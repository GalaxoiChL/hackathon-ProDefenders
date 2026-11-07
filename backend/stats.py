"""Advertiser dashboard numbers: ad spaces, visibility, estimated revenue, cost vs. value.

All money is USD. Every figure that rests on an assumption is listed under `assumptions`,
so the pitch can say exactly where the numbers come from.
"""
from __future__ import annotations

from pathlib import Path

from . import regions
from .config import Settings
from .models import Ad, ClipStats, Manifest, Scene, Surfaces


def polygon_area(corners: list[list[float]]) -> float:
    """Shoelace formula, pixels²."""
    s = 0.0
    for (x1, y1), (x2, y2) in zip(corners, corners[1:] + corners[:1]):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def probe_video(path: Path) -> ClipStats | None:
    """Frame count / fps / size straight from the file (OpenCV is optional for the backend)."""
    try:
        import cv2  # noqa: PLC0415
    except ImportError:
        return None
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return None
    try:
        return ClipStats(
            frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or None,
            fps=cap.get(cv2.CAP_PROP_FPS) or None,
            width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or None,
            height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or None,
        )
    finally:
        cap.release()


def clip_stats(settings: Settings, manifest: Manifest, surfaces: Surfaces | None,
               scene: Scene | None, ads: list[Ad], views: int) -> dict:
    st = manifest.stats or ClipStats()
    if (st.frames is None or st.fps is None) and manifest.regions:
        probed = probe_video(settings.root / manifest.regions[0].video)
        if probed:
            st = ClipStats(**{**probed.model_dump(), **st.model_dump(exclude_none=True)})

    frames, fps = st.frames, st.fps
    duration = frames / fps if frames and fps else None
    if frames and st.lost_frames is not None:
        visibility = max(0.0, (frames - st.lost_frames) / frames)
        visibility_measured = True
    else:
        visibility = 1.0          # engine did not report it; assume always visible
        visibility_measured = False
    visible_seconds = duration * visibility if duration else None

    frame_area = st.width * st.height if st.width and st.height else None
    spaces = []
    for s in (surfaces.surfaces if surfaces else []):
        area = polygon_area(s.corners)
        spaces.append({
            "id": s.id, "type": s.type, "confidence": s.confidence,
            "area_px": round(area),
            "frame_share_pct": round(100 * area / frame_area, 2) if frame_area else None,
            "source": getattr(s, "source", None) or getattr(surfaces, "source", None) or "ai",
        })

    ad_by_id = {a.id: a for a in ads}
    safe = scene.brand_safety.safe if scene else True
    per_region, total_rev = [], 0.0
    for r in manifest.regions:
        meta = regions.REGIONS.get(r.code.upper(), {})
        cpm = meta.get("cpm_usd", 5.0)
        impressions = round(views * visibility) if safe else 0
        revenue = impressions * cpm / 1000 * max(1, len(spaces))
        total_rev += revenue
        ad = ad_by_id.get(r.ad_id) if r.ad_id else None
        per_region.append({
            "code": r.code, "label": r.label or regions.label(r.code),
            "ad_id": r.ad_id, "brand": ad.brand if ad else None, "reason": r.reason,
            "views": views, "impressions": impressions, "cpm_usd": cpm,
            "revenue_usd": round(revenue, 2),
        })

    placements = len(manifest.regions) * max(1, len(spaces))
    ai_cost = placements * settings.ai_cost_per_placement
    manual_cost = placements * settings.manual_hours_per_placement * settings.editor_hourly_rate
    return {
        "clip": manifest.clip,
        "video": {"frames": frames, "fps": fps, "duration_s": round(duration, 2) if duration else None,
                  "width": st.width, "height": st.height},
        "visibility": {"ratio": round(visibility, 3), "visible_seconds": round(visible_seconds, 2)
                       if visible_seconds else None, "measured": visibility_measured},
        "brand_safety": scene.brand_safety.model_dump() if scene else {"safe": True, "reasons": [], "checked": False},
        "spaces": spaces,
        "regions": per_region,
        "totals": {"placements": placements, "revenue_usd": round(total_rev, 2)},
        "cost_vs_value": {
            "ai_cost_usd": round(ai_cost, 2),
            "manual_cost_usd": round(manual_cost, 2),
            "manual_hours": placements * settings.manual_hours_per_placement,
            "savings_x": round(manual_cost / ai_cost) if ai_cost else None,
        },
        "assumptions": {
            "views_per_region": views,
            "cpm_usd": {k: v["cpm_usd"] for k, v in regions.REGIONS.items()},
            "ai_cost_per_placement_usd": settings.ai_cost_per_placement,
            "manual_hours_per_placement": settings.manual_hours_per_placement,
            "editor_hourly_rate_usd": settings.editor_hourly_rate,
            "unsafe_scene_earns_nothing": True,
        },
    }
