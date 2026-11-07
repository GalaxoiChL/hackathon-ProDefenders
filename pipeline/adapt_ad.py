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


def blurred_fill(img: np.ndarray, cw: int, ch: int) -> np.ndarray:
    """The ad itself, scaled to cover the canvas, heavily blurred and darkened: a background that
    matches the ad's colors (the usual 'blur fill' when a creative doesn't match a format)."""
    h, w = img.shape[:2]
    s = max(cw / w, ch / h)
    big = cv2.resize(img, (max(cw, round(w * s)), max(ch, round(h * s))), interpolation=cv2.INTER_AREA)
    y, x = (big.shape[0] - ch) // 2, (big.shape[1] - cw) // 2
    bg = cv2.GaussianBlur(big[y:y + ch, x:x + cw], (0, 0), max(cw, ch) / 25)
    return cv2.convertScaleAbs(bg, alpha=0.7, beta=0)


def smart_cover(img: np.ndarray, cw: int, ch: int, max_stretch: float = 1.15) -> np.ndarray:
    """Fill the whole canvas with the ad: no bands, no visible distortion.

    1. a mild stretch (at most `max_stretch`, not noticeable) absorbs part of the format gap
    2. the rest is cropped, sliding the crop window to where the ad has the most detail
       (text, logo, product = most edges), so the important part stays on the billboard
    """
    h, w = img.shape[:2]
    target, src = cw / ch, w / h
    stretch = min(max_stretch, max(src / target, target / src))
    if src > target:   # ad wider than the surface: squeeze horizontally a bit, then crop width
        img = cv2.resize(img, (max(1, round(w / stretch)), h), interpolation=cv2.INTER_AREA)
    elif src < target:  # ad taller than the surface: squeeze vertically a bit, then crop height
        img = cv2.resize(img, (w, max(1, round(h / stretch))), interpolation=cv2.INTER_AREA)
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    energy = cv2.magnitude(cv2.Sobel(gray, cv2.CV_32F, 1, 0), cv2.Sobel(gray, cv2.CV_32F, 0, 1))
    if w / h > target:  # crop columns
        win = max(1, round(h * target))
        cols = np.convolve(energy.sum(axis=0), np.ones(win), mode="valid")
        # prefer the center when detail is spread evenly (avoid jumping to one edge)
        center_bias = 1 - 0.15 * np.abs(np.linspace(-1, 1, len(cols)))
        x = int(np.argmax(cols * center_bias))
        img = img[:, x:x + win]
    elif w / h < target:  # crop rows
        win = max(1, round(w / target))
        rows = np.convolve(energy.sum(axis=1), np.ones(win), mode="valid")
        center_bias = 1 - 0.15 * np.abs(np.linspace(-1, 1, len(rows)))
        y = int(np.argmax(rows * center_bias))
        img = img[y:y + win]
    return cv2.resize(img, (cw, ch), interpolation=cv2.INTER_AREA)


def fit_to_aspect(img: np.ndarray, aspect: float, long_side: int = 1200, fill: str = "cover") -> np.ndarray:
    """Return a canvas with width/height == aspect.

    fill="cover": the ad fills the whole surface (smart crop + mild stretch) - default
    fill="blur":  the whole ad, centered, with a blurred version of itself around it
    fill="color": the whole ad, centered, with its edge color around it
    """
    if aspect >= 1:
        cw, ch = long_side, max(1, round(long_side / aspect))
    else:
        cw, ch = max(1, round(long_side * aspect)), long_side
    if fill == "cover":
        return smart_cover(img, cw, ch)
    if fill == "blur":
        canvas = blurred_fill(img, cw, ch)
    else:
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
    ap.add_argument("--fill", choices=["cover", "blur", "color"], default="cover")
    args = ap.parse_args()
    img = cv2.imread(str(args.image), cv2.IMREAD_COLOR)
    if img is None:
        raise SystemExit(f"cannot read {args.image}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(args.out), fit_to_aspect(img, args.aspect, fill=args.fill))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
