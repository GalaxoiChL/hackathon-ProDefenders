"""Movies marketplace: every rendered clip is a movie, every ad surface in it is a place, and
every place is sold separately in each country. Any business can bid on any place from the site.

  GET  /api/movies                         movies table (one row per clip)
  GET  /api/movies/{clip}                  the movie's ad places, each with its offer per country
  GET  /api/movies/{clip}/thumbnail.jpg    a frame of the movie
  GET  /api/movies/{clip}/places/{sid}.jpg the ad place, cut out of the frame, outlined
  POST /api/placements/{id}/bids           open bid: {company, email, amount_usd, category?, message?}

Images are cut from the video with OpenCV and cached in output/thumbs/; without OpenCV (API-only
install) the endpoints answer 404 and the site shows a placeholder.
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import regions
from .config import Settings
from .outreach.bids import Bids
from .store import BadData, NotFound, Store, check_clip

SID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


class OpenBid(BaseModel):
    company: str = Field(..., min_length=2, max_length=200)
    email: str = Field(..., max_length=200, description="contact email (kept private)")
    amount_usd: float = Field(..., gt=0, le=10_000_000)
    category: str | None = Field(None, max_length=40, description="e.g. food, retail, beauty")
    message: str | None = Field(None, max_length=2000)


def _title(clip: str) -> str:
    return re.sub(r"[_-]+", " ", clip).strip().title()


class Movies:
    def __init__(self, settings: Settings, store: Store, bids: Bids):
        self.s, self.store, self.bids = settings, store, bids
        self.thumbs = settings.output_dir / "thumbs"
        self._areas: dict[str, float | None] = {}

    # ---------- video files ----------
    def video_path(self, clip: str) -> Path | None:
        """The clean video to cut images from: original, else the source clip, else any version."""
        candidates = [self.s.output_dir / f"{clip}_original.mp4", self.s.clips_dir / f"{clip}.mp4"]
        try:
            m = self.store.manifest(clip)
            if getattr(m, "original", None):
                candidates.insert(0, self.s.root / m.original)
            candidates += [self.s.root / r.video for r in m.regions]
        except (NotFound, BadData):
            pass
        return next((p for p in candidates if p.is_file()), None)

    def video_url(self, clip: str) -> str | None:
        p = self.video_path(clip)
        if p is None:
            return None
        try:
            return "/" + p.resolve().relative_to(self.s.root.resolve()).as_posix()
        except ValueError:
            return None

    def _frame(self, clip: str, index: int = 0):
        try:
            import cv2  # noqa: PLC0415
        except ImportError:
            return None
        path = self.video_path(clip)
        if path is None:
            return None
        cap = cv2.VideoCapture(str(path))
        try:
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, index))
            ok, frame = cap.read()
            return frame if ok else None
        finally:
            cap.release()

    def _duration(self, clip: str) -> float | None:
        try:
            import cv2  # noqa: PLC0415
        except ImportError:
            return None
        path = self.video_path(clip)
        if path is None:
            return None
        cap = cv2.VideoCapture(str(path))
        try:
            n, fps = cap.get(cv2.CAP_PROP_FRAME_COUNT), cap.get(cv2.CAP_PROP_FPS)
            return round(n / fps, 1) if n and fps else None
        finally:
            cap.release()

    # ---------- images ----------
    def thumbnail(self, clip: str) -> Path | None:
        out = self.thumbs / f"{clip}.jpg"
        src = self.video_path(clip)
        if out.is_file() and src and out.stat().st_mtime >= src.stat().st_mtime:
            return out
        frame = self._frame(clip, 15)
        if frame is None:
            return None
        import cv2  # noqa: PLC0415
        h, w = frame.shape[:2]
        frame = cv2.resize(frame, (640, round(640 * h / w)), interpolation=cv2.INTER_AREA)
        self.thumbs.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out), frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
        return out

    def place_image(self, clip: str, sid: str) -> Path | None:
        """The ad place cut out of its frame, with some context around it and the outline drawn."""
        surface = next((x for x in self.bids.surfaces(clip) if x["id"] == sid), None)
        if not surface or not surface.get("corners"):
            return None
        out = self.thumbs / f"{clip}__{sid}.jpg"
        src = self.video_path(clip)
        if out.is_file() and src and out.stat().st_mtime >= src.stat().st_mtime:
            return out
        frame = self._frame(clip, surface.get("frame") or 0)
        if frame is None:
            return None
        import cv2  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415
        q = np.float32(surface["corners"])
        H, W = frame.shape[:2]
        x0, y0 = q.min(0)
        x1, y1 = q.max(0)
        pad = 0.9 * max(x1 - x0, y1 - y0)
        X0, Y0 = int(max(0, x0 - pad)), int(max(0, y0 - pad))
        X1, Y1 = int(min(W, x1 + pad)), int(min(H, y1 + pad))
        dim = (frame * 0.55).astype(np.uint8)          # darken the context, keep the place bright
        mask = np.zeros((H, W), np.uint8)
        cv2.fillPoly(mask, [q.astype(np.int32)], 255)
        dim[mask > 0] = frame[mask > 0]
        cv2.polylines(dim, [q.astype(np.int32)], True, (60, 220, 255), max(2, int(0.006 * W)), cv2.LINE_AA)
        crop = dim[Y0:Y1, X0:X1]
        scale = 480 / max(crop.shape[:2])
        crop = cv2.resize(crop, (round(crop.shape[1] * scale), round(crop.shape[0] * scale)),
                          interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
        self.thumbs.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out), crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return out

    # ---------- data ----------
    def _scene(self, clip: str) -> dict | None:
        try:
            sc = self.store.scene_or_none(clip)
        except BadData:
            return None
        if not sc:
            return None
        return {k: getattr(sc, k) for k in ("location", "time_of_day", "weather", "mood")} | {
            "brand_safe": sc.brand_safety.safe}

    def _frame_area(self, clip: str) -> float | None:
        if clip not in self._areas:
            frame = self._frame(clip, 0)
            self._areas[clip] = float(frame.shape[0] * frame.shape[1]) if frame is not None else None
        return self._areas[clip]

    def places(self, clip: str) -> list[dict]:
        offers = self.bids.placements(clip)
        area = self._frame_area(clip)
        out = []
        for i, sf in enumerate(self.bids.surfaces(clip), 1):
            share = None
            if sf.get("corners") and area:
                xs, ys = zip(*sf["corners"])
                a = abs(sum(xs[k] * ys[(k + 1) % 4] - xs[(k + 1) % 4] * ys[k] for k in range(4))) / 2
                share = round(100 * a / area, 2)
            mine = [o for o in offers if o["surface_id"] == sf["id"]]
            out.append({
                "id": sf["id"], "label": f"Ad place {i}", "type": sf["type"], "confidence": sf["confidence"],
                "aspect": sf["aspect"], "frame_share_pct": share,
                "image_url": f"/api/movies/{clip}/places/{sf['id']}.jpg" if sf.get("corners") else None,
                "bids": sum(o["bids"] for o in mine),
                "top_bid_usd": max((o["top_bid_usd"] or 0 for o in mine), default=0) or None,
                "offers": mine,
            })
        return out

    def summary(self, clip: str) -> dict:
        places = self.places(clip)
        offers = [o for p in places for o in p["offers"]]
        return {
            "clip": clip, "title": _title(clip),
            "thumbnail_url": f"/api/movies/{clip}/thumbnail.jpg", "video_url": self.video_url(clip),
            "duration_s": self._duration(clip), "scene": self._scene(clip),
            "places": len(places), "markets": list(self.s.markets),
            "placements": len(offers), "bids": sum(o["bids"] for o in offers),
            "top_bid_usd": max((o["top_bid_usd"] or 0 for o in offers), default=0) or None,
            "min_floor_usd": min((o["floor_usd"] for o in offers), default=None),
        }

    def detail(self, clip: str) -> dict:
        return self.summary(clip) | {"places": self.places(clip)}


def router(settings: Settings, store: Store, bids: Bids) -> APIRouter:
    movies = Movies(settings, store, bids)
    r = APIRouter(tags=["marketplace"])

    def known(clip: str) -> str:
        check_clip(clip)
        if clip not in bids.clips():
            raise HTTPException(404, f"no movie {clip!r}")
        return clip

    @r.get("/api/movies", summary="Filmele scoase la vânzare: un rând pe clip, cu locurile de reclamă și ofertele")
    def list_movies():
        return [movies.summary(c) for c in bids.clips()]

    @r.get("/api/movies/{clip}", summary="Locurile de reclamă din film și oferta pentru fiecare țară")
    def get_movie(clip: str):
        return movies.detail(known(clip))

    @r.get("/api/movies/{clip}/thumbnail.jpg", include_in_schema=False)
    def thumbnail(clip: str):
        p = movies.thumbnail(known(clip))
        if p is None:
            raise HTTPException(404, "no video to take a thumbnail from")
        return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "max-age=300"})

    @r.get("/api/movies/{clip}/places/{sid}.jpg", include_in_schema=False)
    def place_image(clip: str, sid: str):
        if not SID_RE.match(sid):
            raise HTTPException(404, "bad place id")
        p = movies.place_image(known(clip), sid)
        if p is None:
            raise HTTPException(404, "no image for this place")
        return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "max-age=300"})

    @r.post("/api/placements/{pid}/bids", summary="Ofertă deschisă: orice firmă licitează pe un loc, într-o țară")
    def open_bid(pid: str, req: OpenBid):
        return bids.place_open(pid, req.company, req.email, req.amount_usd, req.message, req.category)

    return r


__all__ = ["Movies", "OpenBid", "router", "regions"]
