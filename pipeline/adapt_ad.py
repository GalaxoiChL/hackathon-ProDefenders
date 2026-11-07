"""Fit an ad image to a surface's aspect ratio WITHOUT distorting it (the safe fallback).

Task 2 replaces this with AI recomposition (extending the background around the real ad).
Until then, and whenever the image API is unavailable, the ad is scaled to fit and the
leftover space is filled with the ad's own dominant edge color, so nothing gets stretched.

    python pipeline/adapt_ad.py data/creatives/ro-pizza-hut.jpg --aspect 0.74 --out out.png
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def dominant_edge_color(img: np.ndarray) -> tuple[int, int, int]:
    """Median color of the outer border: blends best with what the ad already has at its edges."""
    b = max(2, min(img.shape[:2]) // 50)
    edge = np.concatenate([img[:b].reshape(-1, 3), img[-b:].reshape(-1, 3),
                           img[:, :b].reshape(-1, 3), img[:, -b:].reshape(-1, 3)])
    return tuple(int(v) for v in np.median(edge, axis=0))


def fit_to_aspect(img: np.ndarray, aspect: float, long_side: int = 1200) -> np.ndarray:
    """Return a canvas with width/height == aspect, the ad centered inside it, undistorted."""
    if aspect >= 1:
        cw, ch = long_side, max(1, round(long_side / aspect))
    else:
        cw, ch = max(1, round(long_side * aspect)), long_side
    canvas = np.full((ch, cw, 3), dominant_edge_color(img), np.uint8)
    h, w = img.shape[:2]
    s = min(cw / w, ch / h)
    nw, nh = max(1, round(w * s)), max(1, round(h * s))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
    x, y = (cw - nw) // 2, (ch - nh) // 2
    canvas[y:y + nh, x:x + nw] = resized
    return canvas


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("image", type=Path)
    ap.add_argument("--aspect", type=float, required=True, help="surface width / height")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    img = cv2.imread(str(args.image), cv2.IMREAD_COLOR)
    if img is None:
        raise SystemExit(f"cannot read {args.image}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(args.out), fit_to_aspect(img, args.aspect))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
