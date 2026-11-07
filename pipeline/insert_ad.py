"""Insert region-specific ads onto a planar surface (billboard) in a video.

One pass over the video computes the tracking and the occluder masks once,
then renders one output video per region, plus an optional "AI view" debug video.

Example:
    python pipeline/insert_ad.py assets/clips/street.mp4 --corners assets/clips/street.corners.json \
        --ad ro=assets/ads/ro.png --ad us=assets/ads/us.png --ad jp=assets/ads/jp.png \
        --out output/street --track --occlude --debug
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np

# COCO class ids that count as foreground occluders (things that pass in front of the billboard)
OCCLUDER_CLASSES = {"person": 0, "bicycle": 1, "car": 2, "motorcycle": 3, "bus": 5, "truck": 7}


def load_corners(path: Path, surface_id: str | None = None) -> np.ndarray:
    """Corners in order TL, TR, BR, BL, in original-frame pixel coordinates.

    Accepts either a manual corners file ({"corners": [...]}) or the AI detector's
    surfaces file ({"surfaces": [...]}); for the latter it takes `surface_id`, or the
    most confident surface when no id is given.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if "surfaces" in data:
        surfaces = data["surfaces"]
        if not surfaces:
            raise SystemExit(f"{path}: the detector found no ad surfaces")
        if surface_id:
            match = [s for s in surfaces if s["id"] == surface_id]
            if not match:
                raise SystemExit(f"{path}: no surface {surface_id!r}; have {[s['id'] for s in surfaces]}")
            data = match[0]
        else:
            data = max(surfaces, key=lambda s: s.get("confidence", 0))
        print(f"using surface {data['id']} ({data.get('type')}, confidence {data.get('confidence')})")
    pts = np.float32(data["corners"])
    if pts.shape != (4, 2):
        raise ValueError(f"{path}: expected 4 [x, y] corners, got shape {pts.shape}")
    return pts


def plausible(prev: np.ndarray, new: np.ndarray, shape: tuple[int, int]) -> bool:
    """Reject homographies that blow the billboard up, flip it, or fling it far off-screen."""
    if not cv2.isContourConvex(new.reshape(-1, 1, 2).astype(np.float32)):
        return False
    a_prev = cv2.contourArea(prev.astype(np.float32))
    a_new = cv2.contourArea(new.astype(np.float32))
    if a_prev <= 1 or not (0.75 < a_new / a_prev < 1.33):  # per-frame size change
        return False
    h, w = shape
    return a_new < 0.5 * w * h  # a billboard never fills half the frame in our clips


class PlaneTracker:
    """Tracks the billboard plane with LK optical flow + RANSAC homography, frame to frame.

    Features are taken from the billboard polygon dilated by `pad` (the surrounding facade is
    roughly the same plane and gives more texture), excluding pixels covered by occluders.

    When tracking becomes unreliable (too few inliers, implausible jump, billboard off-screen),
    the tracker reports the billboard as lost (`update` returns None) and tries every frame to
    re-acquire it by SIFT-matching against the billboard as it looked in the first frame.
    """

    MIN_INLIERS = 12
    MIN_REACQUIRE_INLIERS = 15

    def __init__(self, first_gray: np.ndarray, corners: np.ndarray, pad: float = 0.35):
        self.prev = first_gray
        self.corners: np.ndarray | None = corners.astype(np.float32).copy()
        self.pad = pad
        self.pts = self._features(first_gray, None)
        self.last_inliers = 0
        # reference "fingerprint" of the billboard for re-acquisition
        # no feature cap: with a cap the strongest features land elsewhere in the frame and a
        # small billboard ends up with ~5 reference points (re-acquire then never succeeds)
        self.sift = cv2.SIFT_create()
        self.ref_corners = self.corners.copy()
        self.ref_kp, self.ref_des = self.sift.detectAndCompute(first_gray, self._region_mask(first_gray.shape))
        self.matcher = cv2.BFMatcher(cv2.NORM_L2)

    @property
    def lost(self) -> bool:
        return self.corners is None

    def _reacquire(self, gray: np.ndarray) -> np.ndarray | None:
        if self.ref_des is None or len(self.ref_kp) < 10:
            return None
        kp, des = self.sift.detectAndCompute(gray, None)
        if des is None or len(kp) < 10:
            return None
        good = [m for m, n in (p for p in self.matcher.knnMatch(self.ref_des, des, k=2) if len(p) == 2)
                if m.distance < 0.75 * n.distance]
        if len(good) < self.MIN_REACQUIRE_INLIERS:
            return None
        src = np.float32([self.ref_kp[m.queryIdx].pt for m in good])
        dst = np.float32([kp[m.trainIdx].pt for m in good])
        H, inl = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
        if H is None or inl.sum() < self.MIN_REACQUIRE_INLIERS:
            return None
        found = cv2.perspectiveTransform(self.ref_corners.reshape(-1, 1, 2), H).reshape(4, 2)
        if not cv2.isContourConvex(found.reshape(-1, 1, 2)):
            return None
        self.last_inliers = int(inl.sum())
        return found

    def _region_mask(self, shape: tuple[int, int]) -> np.ndarray:
        center = self.corners.mean(axis=0)
        grown = center + (self.corners - center) * (1.0 + self.pad)
        mask = np.zeros(shape, np.uint8)
        cv2.fillConvexPoly(mask, grown.astype(np.int32), 255)
        return mask

    def _features(self, gray: np.ndarray, exclude: np.ndarray | None) -> np.ndarray | None:
        mask = self._region_mask(gray.shape)
        if exclude is not None:
            mask[exclude > 0] = 0
        return cv2.goodFeaturesToTrack(gray, maxCorners=500, qualityLevel=0.01, minDistance=6, mask=mask)

    def update(self, gray: np.ndarray, exclude: np.ndarray | None) -> np.ndarray | None:
        if self.lost:
            found = self._reacquire(gray)
            self.prev = gray
            if found is not None:
                self.corners = found
                self.pts = self._features(gray, exclude)
            return self.corners
        tracked = False
        if self.pts is not None and len(self.pts) >= 8:
            nxt, st, _ = cv2.calcOpticalFlowPyrLK(
                self.prev, gray, self.pts, None, winSize=(21, 21), maxLevel=3,
                criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
            )
            ok = st.reshape(-1) == 1
            old, new = self.pts[ok], nxt[ok]
            if exclude is not None and len(new):
                # drop points that landed on an occluder in the new frame
                xy = np.clip(new.reshape(-1, 2).round().astype(int), 0, [gray.shape[1] - 1, gray.shape[0] - 1])
                keep = exclude[xy[:, 1], xy[:, 0]] == 0
                old, new = old[keep], new[keep]
            if len(new) >= 8:
                H, inl = cv2.findHomography(old, new, cv2.RANSAC, 3.0)
                if H is not None and inl.sum() >= self.MIN_INLIERS:
                    moved = cv2.perspectiveTransform(self.corners.reshape(-1, 1, 2), H).reshape(4, 2)
                    if plausible(self.corners, moved, gray.shape):
                        self.corners = moved
                        self.last_inliers = int(inl.sum())
                        tracked = True
        self.prev = gray
        if not tracked:
            self.corners = None  # lost: stop drawing, try to re-acquire from next frame
            self.last_inliers = 0
            self.pts = None
            return None
        self.pts = self._features(gray, exclude)
        return self.corners


class Occluders:
    """Person/vehicle segmentation with YOLO, so people walking in front stay in front of the ad."""

    def __init__(self, classes: list[str], weights: str = "yolo11n-seg.pt"):
        from ultralytics import YOLO  # imported lazily: slow import, optional feature

        self.model = YOLO(weights)
        self.class_ids = [OCCLUDER_CLASSES[c] for c in classes]

    def mask(self, frame: np.ndarray, box: tuple[int, int, int, int], billboard: np.ndarray) -> np.ndarray:
        """Full-frame occluder mask, but only computed inside `box` (only there can it cover the ad).

        People that sit (almost) entirely inside the billboard polygon are part of the OLD ad's
        picture, not real people in front of it, so they are ignored.
        """
        h, w = frame.shape[:2]
        full = np.zeros((h, w), np.uint8)
        x0, y0, x1, y1 = box
        crop = frame[y0:y1, x0:x1]
        if crop.size == 0:
            return full
        res = self.model.predict(crop, classes=self.class_ids, retina_masks=True, verbose=False)[0]
        if res.masks is None:
            return full
        inst = res.masks.data.cpu().numpy() > 0.5  # (n, mh, mw)
        if inst.shape[1:] != crop.shape[:2]:
            inst = np.stack([cv2.resize(i.astype(np.uint8), (crop.shape[1], crop.shape[0]),
                                        interpolation=cv2.INTER_NEAREST) > 0 for i in inst])
        poly = np.zeros(crop.shape[:2], np.uint8)
        cv2.fillConvexPoly(poly, (billboard - [x0, y0]).astype(np.int32), 1)
        poly = poly.astype(bool)
        keep = [i for i in inst if i.sum() and (i & poly).sum() / i.sum() < 0.85]
        if not keep:
            return full
        m = np.any(keep, axis=0).astype(np.uint8) * 255
        # grow slightly so hair/edges do not leave a halo of ad around the person
        full[y0:y1, x0:x1] = cv2.dilate(m, np.ones((5, 5), np.uint8))
        return full


def roi_box(corners: np.ndarray, w: int, h: int, pad: float) -> tuple[int, int, int, int]:
    """Axis-aligned box around the billboard, grown by `pad` (fraction of its size), clipped to the frame."""
    x0, y0 = corners.min(axis=0)
    x1, y1 = corners.max(axis=0)
    px, py = (x1 - x0) * pad + 4, (y1 - y0) * pad + 4
    return (int(max(0, x0 - px)), int(max(0, y0 - py)), int(min(w, x1 + px + 1)), int(min(h, y1 + py + 1)))


def harmonize(ad: np.ndarray, frame: np.ndarray, mask: np.ndarray, strength: float) -> np.ndarray:
    """Pull the ad's brightness/contrast toward what the original billboard area looked like.

    Only luminance (L) is matched: the old ad's colors are its own content, not scene lighting,
    so copying its tint would recolor our ad (red came out orange in the synthetic test).
    """
    sel = mask > 0
    if strength <= 0 or sel.sum() < 50:
        return ad
    ad_lab = cv2.cvtColor(ad, cv2.COLOR_BGR2LAB).astype(np.float32)
    fr_lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB).astype(np.float32)
    out = ad_lab.copy()
    for ch, s in ((0, strength),):
        a_mu, a_sd = ad_lab[..., ch][sel].mean(), ad_lab[..., ch][sel].std() + 1e-6
        f_mu, f_sd = fr_lab[..., ch][sel].mean(), fr_lab[..., ch][sel].std() + 1e-6
        target_sd = a_sd + (min(f_sd, a_sd) - a_sd) * s  # only ever reduce contrast (scene haze), never boost
        moved = (ad_lab[..., ch] - a_mu) * (target_sd / a_sd) + (a_mu + (f_mu - a_mu) * s)
        out[..., ch] = moved
    return cv2.cvtColor(np.clip(out, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)


def composite(frame, ad_img, corners, occ_mask, harmonize_strength, blur_sigma):
    """Paste the ad onto the billboard. All the work happens in a small box around the billboard."""
    h, w = frame.shape[:2]
    out = frame.copy()
    x0, y0, x1, y1 = roi_box(corners, w, h, pad=0.02)
    if x1 <= x0 or y1 <= y0:
        return out  # billboard fully off-screen
    rw, rh = x1 - x0, y1 - y0
    roi = frame[y0:y1, x0:x1]
    ah, aw = ad_img.shape[:2]
    src = np.float32([[0, 0], [aw, 0], [aw, ah], [0, ah]])
    M = cv2.getPerspectiveTransform(src, (corners - [x0, y0]).astype(np.float32))
    warped = cv2.warpPerspective(ad_img, M, (rw, rh), flags=cv2.INTER_LINEAR)
    mask = cv2.warpPerspective(np.full((ah, aw), 255, np.uint8), M, (rw, rh), flags=cv2.INTER_LINEAR)
    warped = harmonize(warped, roi, mask, harmonize_strength)
    if blur_sigma > 0:
        warped = cv2.GaussianBlur(warped, (0, 0), blur_sigma)
    alpha = cv2.GaussianBlur(mask, (3, 3), 0).astype(np.float32) / 255.0  # anti-aliased edges
    if occ_mask is not None:
        occ = cv2.GaussianBlur(occ_mask[y0:y1, x0:x1], (5, 5), 0).astype(np.float32) / 255.0
        alpha *= 1.0 - occ
    alpha = alpha[..., None]
    out[y0:y1, x0:x1] = (roi.astype(np.float32) * (1 - alpha) + warped.astype(np.float32) * alpha).astype(np.uint8)
    return out


def draw_debug(frame, corners, occ_mask, label):
    out = frame.copy()
    if occ_mask is not None and occ_mask.any():
        tint = out.copy()
        tint[occ_mask > 0] = (0.5 * tint[occ_mask > 0] + 0.5 * np.array([255, 80, 200])).astype(np.uint8)
        out = tint
    cv2.polylines(out, [corners.astype(np.int32)], True, (0, 255, 0), 3, cv2.LINE_AA)
    for p in corners:
        cv2.circle(out, tuple(int(v) for v in p), 6, (0, 255, 255), -1, cv2.LINE_AA)
    cv2.putText(out, label, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2, cv2.LINE_AA)
    return out


def ffmpeg_exe() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def finalize(tmp_video: Path, source: Path, out: Path) -> None:
    """Re-encode to browser-friendly H.264 and copy the original audio track if there is one."""
    cmd = [
        ffmpeg_exe(), "-y", "-loglevel", "error",
        "-i", str(tmp_video), "-i", str(source),
        "-map", "0:v:0", "-map", "1:a:0?",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "veryfast",
        "-c:a", "aac", "-shortest", "-movflags", "+faststart", str(out),
    ]
    subprocess.run(cmd, check=True)
    tmp_video.unlink(missing_ok=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("--corners", type=Path, required=True,
                    help="corners JSON (manual) or surfaces JSON from detect_surfaces.py, on the first frame")
    ap.add_argument("--surface", help="surface id to use from a surfaces JSON (default: most confident)")
    ap.add_argument("--ad", action="append", required=True, help="region=path/to/ad.png (repeatable)")
    ap.add_argument("--out", type=Path, required=True, help="output prefix, e.g. output/street -> output/street_ro.mp4")
    ap.add_argument("--track", action="store_true", help="track the billboard (moving camera)")
    ap.add_argument("--occlude", action="store_true", help="keep people/vehicles in front of the ad (YOLO)")
    ap.add_argument("--occluders", default="person", help="comma list: " + ",".join(OCCLUDER_CLASSES))
    ap.add_argument("--harmonize", type=float, default=0.5, help="0..1 color/brightness match to the scene")
    ap.add_argument("--blur", type=float, default=0.6, help="gaussian sigma applied to the ad (camera softness)")
    ap.add_argument("--debug", action="store_true", help="also render the 'AI view' video")
    ap.add_argument("--max-frames", type=int, default=0)
    args = ap.parse_args()

    ads = {}
    for spec in args.ad:
        region, _, path = spec.partition("=")
        img = cv2.imread(path, cv2.IMREAD_COLOR)
        if img is None:
            raise SystemExit(f"cannot read ad image: {path}")
        ads[region] = img

    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        raise SystemExit(f"cannot open video: {args.video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    corners = load_corners(args.corners, args.surface)
    occ = Occluders(args.occluders.split(",")) if args.occlude else None

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writers, tmp_paths = {}, {}
    names = list(ads) + (["ai_view"] if args.debug else [])
    for name in names:
        tmp_paths[name] = args.out.parent / f"{args.out.name}_{name}.tmp.mp4"
        writers[name] = cv2.VideoWriter(str(tmp_paths[name]), fourcc, fps, (w, h))

    tracker = None
    idx = lost_frames = 0
    limit = min(total, args.max_frames) if args.max_frames and total else (args.max_frames or total)
    while True:
        ok, frame = cap.read()
        if not ok or (args.max_frames and idx >= args.max_frames):
            break
        occ_mask = None
        if occ and corners is not None:
            occ_mask = occ.mask(frame, roi_box(corners, w, h, pad=0.6), corners)
        if args.track:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if tracker is None:
                tracker = PlaneTracker(gray, corners)
            else:
                corners = tracker.update(gray, occ_mask)
        if corners is None:
            lost_frames += 1
        for region, ad_img in ads.items():
            out = frame if corners is None else composite(frame, ad_img, corners, occ_mask, args.harmonize, args.blur)
            writers[region].write(out)
        if args.debug:
            if corners is None:
                dbg = frame.copy()
                cv2.putText(dbg, f"frame {idx}  billboard LOST - searching", (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2, cv2.LINE_AA)
            else:
                dbg = draw_debug(frame, corners, occ_mask, f"frame {idx}  inliers {tracker.last_inliers if tracker else '-'}")
            writers["ai_view"].write(dbg)
        idx += 1
        if idx % 30 == 0:
            print(f"  {idx}/{limit or '?'} frames  (lost so far: {lost_frames})", flush=True)
    cap.release()
    for wr in writers.values():
        wr.release()

    for name in names:
        out = args.out.parent / f"{args.out.name}_{name}.mp4"
        finalize(tmp_paths[name], args.video, out)
        print(f"wrote {out}")
    print(f"frames: {idx}, billboard lost in {lost_frames}")
    print("last corners:", None if corners is None else np.round(corners, 1).tolist())


if __name__ == "__main__":
    main()
