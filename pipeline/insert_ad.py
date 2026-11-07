"""Insert region-specific ads onto a planar surface (billboard) in a video.

One pass over the video computes the tracking and the occluder masks once,
then renders one output video per region, plus an optional "AI view" debug video.

Example:
    python pipeline/insert_ad.py assets/clips/street.mp4 --corners assets/clips/street.corners.json \
        --ad ro=data/creatives/ro-pizza-hut.jpg --ad jp=data/creatives/jp-mcdonalds.jpg \
        --out output/street --track --occlude --debug
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np

FADE_OUT = 0.25  # ad fades out over 4 frames (~0.13 s at 30 fps)
FADE_IN = 0.5    # and back in over 2 frames: the old ad must not show through for long

# COCO class ids that count as foreground occluders (things that pass in front of the billboard)
OCCLUDER_CLASSES = {"person": 0, "bicycle": 1, "car": 2, "motorcycle": 3, "bus": 5, "truck": 7}


def grow_quad(corners: np.ndarray, frac: float) -> np.ndarray:
    """Push the quad outward from its center, so the new ad fully covers the old billboard's frame.

    Detected corners tend to sit a few pixels inside the frame, which left a thin strip of the
    original billboard visible along the edges.
    """
    if frac <= 0:
        return corners
    center = corners.mean(axis=0)
    return (center + (corners - center) * (1.0 + frac)).astype(np.float32)


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


def quad_aspect(q: np.ndarray) -> float:
    w = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / 2
    h = (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1])) / 2
    return float(w / max(h, 1e-6))


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
    # measured on the Melbourne clip: when the billboard comes back it matches with 8-14 inliers
    # (motion blur, partly cut by the frame edge); the shape checks in _reacquire guard false hits
    MIN_REACQUIRE_INLIERS = 8
    MAX_BLIND_FRAMES = 45  # bus fills the whole frame: hold the last position up to ~1.5 s

    def __init__(self, first_gray: np.ndarray, corners: np.ndarray, pad: float = 0.35):
        self.prev = first_gray
        self.corners: np.ndarray | None = corners.astype(np.float32).copy()
        self.pad = pad
        self.pts = self._features(first_gray, None)
        self.last_inliers = 0
        self.mode = "local"
        self.coast_frames = 0
        self.blind_frames = 0
        self.prev_exclude: np.ndarray | None = None
        # reference "fingerprint" of the billboard for re-acquisition
        # no feature cap: with a cap the strongest features land elsewhere in the frame and a
        # small billboard ends up with ~5 reference points (re-acquire then never succeeds)
        self.sift = cv2.SIFT_create()
        self.ref_corners = self.corners.copy()
        self.ref_kp, self.ref_des = self.sift.detectAndCompute(first_gray, self._region_mask(first_gray.shape))
        self.matcher = cv2.BFMatcher(cv2.NORM_L2)

    MIN_GLOBAL_INLIERS = 30
    MAX_COAST_FRAMES = 600  # give up dead-reckoning after ~20 s without seeing the billboard

    @property
    def lost(self) -> bool:
        return self.corners is None

    def _global_motion(self, gray: np.ndarray, exclude: np.ndarray | None) -> np.ndarray | None:
        """Camera motion between the previous and current frame, estimated on the whole scene.

        Moving objects (people, buses) are masked out, so a bus driving past does not drag the
        billboard along with it. Distant buildings move almost as one plane, which is good enough
        to carry the billboard's position while it is hidden or off-screen.
        """
        mask = None
        if self.prev_exclude is not None:
            mask = np.where(self.prev_exclude > 0, 0, 255).astype(np.uint8)
        pts = cv2.goodFeaturesToTrack(self.prev, maxCorners=800, qualityLevel=0.01, minDistance=12, mask=mask)
        if pts is None or len(pts) < self.MIN_GLOBAL_INLIERS:
            return None
        nxt, st, _ = cv2.calcOpticalFlowPyrLK(self.prev, gray, pts, None, winSize=(21, 21), maxLevel=4)
        ok = st.reshape(-1) == 1
        old, new = pts[ok], nxt[ok]
        if exclude is not None and len(new):
            xy = np.clip(new.reshape(-1, 2).round().astype(int), 0, [gray.shape[1] - 1, gray.shape[0] - 1])
            keep = exclude[xy[:, 1], xy[:, 0]] == 0
            old, new = old[keep], new[keep]
        if len(new) < self.MIN_GLOBAL_INLIERS:
            return None
        H, inl = cv2.findHomography(old, new, cv2.RANSAC, 3.0)
        if H is None or inl.sum() < self.MIN_GLOBAL_INLIERS:
            return None
        return H

    def _on_screen(self, shape: tuple[int, int]) -> bool:
        h, w = shape
        x0, y0 = self.corners.min(axis=0)
        x1, y1 = self.corners.max(axis=0)
        return x1 > 0 and y1 > 0 and x0 < w and y0 < h

    def _reacquire(self, gray: np.ndarray) -> np.ndarray | None:
        if self.ref_des is None or len(self.ref_kp) < 10:
            return None
        kp, des = self.sift.detectAndCompute(gray, None)
        if des is None or len(kp) < 10:
            return None
        good = [m for m, n in (p for p in self.matcher.knnMatch(self.ref_des, des, k=2) if len(p) == 2)
                if m.distance < 0.8 * n.distance]
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
        # same billboard => similar shape and size as in the first frame (rejects false matches)
        a_ref, a_new = cv2.contourArea(self.ref_corners), cv2.contourArea(found.astype(np.float32))
        if not (0.3 < a_new / max(a_ref, 1) < 3.0):
            return None
        if not (0.65 < quad_aspect(found) / max(quad_aspect(self.ref_corners), 1e-6) < 1.55):
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
        """Returns the billboard corners for this frame, or None if it is lost.

        mode "local": billboard visible, tracked precisely on its own texture
        mode "coast": billboard hidden (bus in front) or off-screen; its position follows the
                      camera motion, so the ad stays in place behind occluders and is already
                      there when the billboard comes back (no visible switch from the old ad)
        mode "lost":  even camera motion failed; only SIFT re-acquisition can bring it back
        Re-acquisition (SIFT against the first frame) runs while coasting too, to correct drift.
        """
        if self.mode == "local" and self._track_local(gray, exclude):
            self.coast_frames = 0
        else:
            if self.mode == "local":
                self.mode = "coast"
            if self.mode == "coast":
                H = self._global_motion(gray, exclude)
                moved = None if H is None else cv2.perspectiveTransform(self.corners.reshape(-1, 1, 2), H).reshape(4, 2)
                self.coast_frames += 1
                if moved is not None and cv2.isContourConvex(moved.reshape(-1, 1, 2)):
                    self.corners = moved
                    self.blind_frames = 0
                else:  # e.g. the bus fills the frame: no background left to measure camera motion
                    self.blind_frames += 1
                if self.blind_frames > self.MAX_BLIND_FRAMES or self.coast_frames > self.MAX_COAST_FRAMES:
                    self.mode, self.corners = "lost", None
            # snap back to the exact billboard as soon as it is identifiable again
            if self.mode == "lost" or self._on_screen(gray.shape) or self.coast_frames % 10 == 0:
                found = self._reacquire(gray)
                # after a long coast the dead-reckoned position has drifted: trust SIFT + shape checks
                trust = self.corners is None or self.coast_frames > 30 or self._close(found, gray.shape) \
                    if found is not None else False
                if trust:
                    self.corners, self.mode, self.coast_frames, self.blind_frames = found, "local", 0, 0
                    self.pts = self._features(gray, exclude)
        self.prev, self.prev_exclude = gray, exclude
        return self.corners

    def _close(self, found: np.ndarray, shape: tuple[int, int]) -> bool:
        """Accept a re-acquired position only if it agrees with dead-reckoning (guards false matches)."""
        return float(np.abs(found - self.corners).max()) < 0.25 * max(shape)

    def _track_local(self, gray: np.ndarray, exclude: np.ndarray | None) -> bool:
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
        if not tracked:
            self.last_inliers = 0
            self.pts = None
            return False
        self.pts = self._features(gray, exclude)
        return True


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


class ReferenceKeyer:
    """Finds anything in front of the billboard by comparing with how the billboard originally looked.

    We know the exact background (the old ad, captured on the first frame). Where the current frame
    no longer matches it, something is in front: a bus, a person, a pole - even if YOLO missed it.
    This is the classic technique of broadcast virtual advertising, and it does not flicker the way
    a per-frame detector can.
    """

    def __init__(self, first_frame: np.ndarray, corners: np.ndarray, size: int = 256, threshold: float = 32.0):
        self.aspect = quad_aspect(corners)
        self.rw, self.rh = (size, max(8, round(size / self.aspect))) if self.aspect >= 1 \
            else (max(8, round(size * self.aspect)), size)
        rect = np.float32([[0, 0], [self.rw, 0], [self.rw, self.rh], [0, self.rh]])
        M = cv2.getPerspectiveTransform(corners.astype(np.float32), rect)
        ref = cv2.warpPerspective(first_frame, M, (self.rw, self.rh), flags=cv2.INTER_AREA)
        self.ref_lab = cv2.cvtColor(cv2.GaussianBlur(ref, (0, 0), 1.5), cv2.COLOR_BGR2LAB).astype(np.float32)
        self.rect = rect
        self.threshold = threshold

    def mask(self, frame: np.ndarray, corners: np.ndarray) -> tuple[np.ndarray, float]:
        """Full-frame uint8 mask of pixels in front of the billboard, and the covered fraction (0..1)."""
        h, w = frame.shape[:2]
        full = np.zeros((h, w), np.uint8)
        x0, y0, x1, y1 = roi_box(corners, w, h, pad=0.0)
        if x1 - x0 < 4 or y1 - y0 < 4:
            return full, 0.0
        local = (corners - [x0, y0]).astype(np.float32)
        M = cv2.getPerspectiveTransform(self.rect, local)
        size = (x1 - x0, y1 - y0)
        ref = cv2.warpPerspective(self.ref_lab, M, size, flags=cv2.INTER_LINEAR)
        valid = cv2.warpPerspective(np.full((self.rh, self.rw), 255, np.uint8), M, size, flags=cv2.INTER_NEAREST)
        valid = cv2.erode(valid, np.ones((5, 5), np.uint8)) > 0  # ignore the outermost pixels (edge jitter)
        if valid.sum() < 50:
            return full, 0.0
        cur = cv2.cvtColor(cv2.GaussianBlur(frame[y0:y1, x0:x1], (0, 0), 1.5), cv2.COLOR_BGR2LAB).astype(np.float32)
        # absorb global lighting changes: align the median brightness of the two
        ref[..., 0] += np.median(cur[..., 0][valid]) - np.median(ref[..., 0][valid])
        diff = 0.5 * np.abs(cur[..., 0] - ref[..., 0]) + np.abs(cur[..., 1] - ref[..., 1]) + np.abs(cur[..., 2] - ref[..., 2])
        diff = cv2.GaussianBlur(diff, (0, 0), 2.0)
        m = ((diff > self.threshold) & valid).astype(np.uint8) * 255
        # remove speckles from tracking jitter on the old ad's sharp edges, then close small holes
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        n, labels, stats, _ = cv2.connectedComponentsWithStats(m)
        min_area = 0.01 * valid.sum()
        keep = np.zeros(n, bool)
        keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_area
        m = np.where(keep[labels], 255, 0).astype(np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        full[y0:y1, x0:x1] = m
        return full, float((m > 0)[valid].mean())


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


def scene_look(frame: np.ndarray, corners: np.ndarray) -> tuple[np.ndarray, float, float]:
    """Measure the scene around the billboard: air/haze color, saturation level, sensor grain."""
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = roi_box(corners, w, h, pad=0.5)
    ring = frame[y0:y1, x0:x1]
    if ring.size == 0:
        return np.array([128, 128, 128], np.float32), 0.3, 1.5
    air = np.median(ring.reshape(-1, 3), axis=0).astype(np.float32)
    sat = float(np.median(cv2.cvtColor(ring, cv2.COLOR_BGR2HSV)[..., 1])) / 255.0
    gray = cv2.cvtColor(ring, cv2.COLOR_BGR2GRAY).astype(np.float32)
    hp = gray - cv2.GaussianBlur(gray, (0, 0), 1.5)
    grain = float(np.median(np.abs(hp)) * 1.4826)  # robust std of the fine noise
    return air, sat, min(grain, 6.0)


def realism(ad: np.ndarray, air: np.ndarray, scene_sat: float, grain: float, haze: float, rng) -> np.ndarray:
    """Make a clean digital ad look filmed: atmospheric haze, scene-level saturation, sensor grain."""
    out = ad.astype(np.float32)
    # 1. desaturate toward the scene: a saturated print seen through the air looks muted on camera
    hsv = cv2.cvtColor(np.clip(out, 0, 255).astype(np.uint8), cv2.COLOR_BGR2HSV).astype(np.float32)
    ad_sat = max(float(np.median(hsv[..., 1])) / 255.0, 1e-3)
    factor = float(np.clip(0.55 + 0.45 * scene_sat / ad_sat, 0.55, 1.0))
    hsv[..., 1] *= factor
    out = cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32)
    # 2. atmospheric haze: blend a little toward the surrounding air color
    out = out * (1 - haze) + air * haze
    # 3. sensor grain like the rest of the footage
    if grain > 0.2:
        out += rng.normal(0, grain, out.shape[:2])[..., None]
    return np.clip(out, 0, 255).astype(np.uint8)


def composite(frame, ad_img, corners, occ_mask, harmonize_strength, blur_sigma, haze=0.12, rng=None, opacity=1.0):
    """Paste the ad onto the billboard. All the work happens in a small box around the billboard."""
    h, w = frame.shape[:2]
    out = frame.copy()
    x0, y0, x1, y1 = roi_box(corners, w, h, pad=0.02)
    if x1 <= x0 or y1 <= y0:
        return out  # billboard fully off-screen
    rw, rh = x1 - x0, y1 - y0
    roi = frame[y0:y1, x0:x1]
    # shrink the ad to about its on-screen size first (area averaging), like a camera would see it;
    # warping a 1200px image straight down to ~150px aliases and looks unnaturally crisp
    side = float(max(np.linalg.norm(corners[1] - corners[0]), np.linalg.norm(corners[2] - corners[1])))
    scale = min(1.0, 1.5 * side / max(ad_img.shape[:2]))
    if scale < 1.0:
        ad_img = cv2.resize(ad_img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    ah, aw = ad_img.shape[:2]
    src = np.float32([[0, 0], [aw, 0], [aw, ah], [0, ah]])
    M = cv2.getPerspectiveTransform(src, (corners - [x0, y0]).astype(np.float32))
    warped = cv2.warpPerspective(ad_img, M, (rw, rh), flags=cv2.INTER_LINEAR)
    mask = cv2.warpPerspective(np.full((ah, aw), 255, np.uint8), M, (rw, rh), flags=cv2.INTER_LINEAR)
    warped = harmonize(warped, roi, mask, harmonize_strength)
    if blur_sigma > 0:
        warped = cv2.GaussianBlur(warped, (0, 0), blur_sigma)
    if haze > 0:
        air, scene_sat, grain = scene_look(frame, corners)
        warped = realism(warped, air, scene_sat, grain, haze, rng or np.random.default_rng())
    alpha = cv2.GaussianBlur(mask, (3, 3), 0).astype(np.float32) / 255.0 * opacity  # anti-aliased edges, fade
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
    ap.add_argument("--grow", type=float, default=0.02,
                    help="enlarge the surface by this fraction so the old billboard's edges are covered")
    ap.add_argument("--ad", action="append", required=True, help="region=path/to/ad.png (repeatable)")
    ap.add_argument("--out", type=Path, required=True, help="output prefix, e.g. output/street -> output/street_ro.mp4")
    ap.add_argument("--track", action="store_true", help="track the billboard (moving camera)")
    ap.add_argument("--occlude", action="store_true", help="keep people/vehicles in front of the ad (YOLO)")
    ap.add_argument("--occluders", default="person", help="comma list: " + ",".join(OCCLUDER_CLASSES))
    ap.add_argument("--harmonize", type=float, default=0.5, help="0..1 color/brightness match to the scene")
    ap.add_argument("--blur", type=float, default=0.6, help="gaussian sigma applied to the ad (camera softness)")
    ap.add_argument("--haze", type=float, default=0.12,
                    help="0..1 atmospheric haze/desaturation/grain so the ad looks filmed (0 = off)")
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

    corners = grow_quad(load_corners(args.corners, args.surface), args.grow)
    occ = None
    if args.occlude:
        try:
            occ = Occluders(args.occluders.split(","))
        except (OSError, ImportError) as e:
            # e.g. Windows Application Control blocking torch DLLs: keep going, the reference keyer
            # still finds whatever is in front of the billboard (bus, people) without torch
            print(f"WARNING: YOLO occluders unavailable ({type(e).__name__}: {str(e)[:120]}); "
                  "using reference keying only")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writers, tmp_paths = {}, {}
    names = list(ads) + (["ai_view"] if args.debug else [])
    for name in names:
        tmp_paths[name] = args.out.parent / f"{args.out.name}_{name}.tmp.mp4"
        writers[name] = cv2.VideoWriter(str(tmp_paths[name]), fourcc, fps, (w, h))

    tracker = None
    keyer = None
    rng = np.random.default_rng(0)  # fixed seed: identical grain across reruns
    visible, opacity = True, 1.0
    hidden_streak = clear_streak = 0
    idx = lost_frames = coast_count = 0
    limit = min(total, args.max_frames) if args.max_frames and total else (args.max_frames or total)
    while True:
        ok, frame = cap.read()
        if not ok or (args.max_frames and idx >= args.max_frames):
            break
        occ_mask = None
        if occ and corners is not None:
            # while coasting, segment the whole frame: camera motion must ignore the bus everywhere
            coasting = tracker is not None and tracker.mode != "local"
            box = (0, 0, w, h) if coasting else roi_box(corners, w, h, pad=0.6)
            occ_mask = occ.mask(frame, box, corners)
        if args.track:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if tracker is None:
                tracker = PlaneTracker(gray, corners)
            else:
                corners = tracker.update(gray, occ_mask)
        if keyer is None:
            keyer = ReferenceKeyer(frame, corners)
        covered = 0.0
        if corners is not None:
            # what is in front of the billboard: YOLO (people, vehicles) OR "doesn't look like the old ad"
            key_mask, covered = keyer.mask(frame, corners)
            occ_mask = key_mask if occ_mask is None else np.maximum(occ_mask, key_mask)
        # Visibility with hysteresis + fade: deciding per frame made the ad blink on and off when the
        # covered fraction hovered around the threshold. Now it hides only after several covered frames,
        # comes back only after several clear frames, and always fades over a few frames.
        if corners is None or covered > 0.6:
            hidden_streak, clear_streak = hidden_streak + 1, 0
        elif covered < 0.4:
            hidden_streak, clear_streak = 0, clear_streak + 1
        if visible and (corners is None or hidden_streak >= 2):
            visible = False
        elif not visible and corners is not None and clear_streak >= 1:
            visible = True  # come back at once: every extra frame would show the OLD ad (a visible switch)
        opacity = float(np.clip(opacity + (FADE_IN if visible else -FADE_OUT), 0.0, 1.0))
        if corners is None:
            lost_frames += 1
        elif tracker is not None and tracker.mode == "coast":
            coast_count += 1
        for region, ad_img in ads.items():
            draw = corners is not None and opacity > 0
            out = composite(frame, ad_img, corners, occ_mask, args.harmonize, args.blur,
                            haze=args.haze, rng=rng, opacity=opacity) if draw else frame
            writers[region].write(out)
        if args.debug:
            if corners is None:
                dbg = frame.copy()
                cv2.putText(dbg, f"frame {idx}  billboard LOST - searching", (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2, cv2.LINE_AA)
            else:
                if tracker is not None and tracker.mode == "coast":
                    label = f"frame {idx}  hidden/off-screen: following camera motion  covered {covered:.0%}"
                else:
                    label = f"frame {idx}  tracking  inliers {tracker.last_inliers if tracker else '-'}  covered {covered:.0%}"
                dbg = draw_debug(frame, corners, occ_mask, label)
            writers["ai_view"].write(dbg)
        idx += 1
        if idx % 30 == 0:
            line = f"  {idx}/{limit or '?'} frames  (hidden/off-screen: {coast_count}, lost: {lost_frames})"
            print(line, flush=True)
            try:  # fixed location so anyone can watch progress: Get-Content output\progress.txt -Wait
                (args.out.parent / "progress.txt").write_text(f"{args.video.name}: {line.strip()}\n", encoding="utf-8")
            except OSError:
                pass
    cap.release()
    for wr in writers.values():
        wr.release()

    for name in names:
        out = args.out.parent / f"{args.out.name}_{name}.mp4"
        finalize(tmp_paths[name], args.video, out)
        print(f"wrote {out}")
    print(f"frames: {idx}, billboard hidden/off-screen (followed by camera motion) in {coast_count}, lost in {lost_frames}")
    print("last corners:", None if corners is None else np.round(corners, 1).tolist())


if __name__ == "__main__":
    main()
