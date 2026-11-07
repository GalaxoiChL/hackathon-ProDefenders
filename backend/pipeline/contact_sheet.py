"""Build a comparison image from rendered outputs: rows = frames, columns = versions.

    python pipeline/contact_sheet.py output/melbourne --versions ro us jp ai_view --frames 0 160 320 470 \
        --crop 900 250 1400 700 --out output/melbourne_sheet.jpg
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def grab(path: Path, idx: int) -> np.ndarray:
    cap = cv2.VideoCapture(str(path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit(f"cannot read frame {idx} of {path}")
    return frame


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("prefix", type=Path, help="e.g. output/melbourne (reads output/melbourne_<version>.mp4)")
    ap.add_argument("--versions", nargs="+", default=["ro", "us", "ai_view"])
    ap.add_argument("--frames", nargs="+", type=int, default=[0, 100, 200])
    ap.add_argument("--crop", nargs=4, type=int, metavar=("X0", "Y0", "X1", "Y1"), help="zoom into a region")
    ap.add_argument("--cell-width", type=int, default=420)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    rows = []
    for idx in args.frames:
        cells = []
        for v in args.versions:
            f = grab(args.prefix.parent / f"{args.prefix.name}_{v}.mp4", idx)
            if args.crop:
                x0, y0, x1, y1 = args.crop
                f = f[y0:y1, x0:x1]
            scale = args.cell_width / f.shape[1]
            f = cv2.resize(f, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            cv2.putText(f, f"{v} #{idx}", (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4, cv2.LINE_AA)
            cv2.putText(f, f"{v} #{idx}", (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
            cells.append(f)
        rows.append(np.hstack(cells))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(args.out), np.vstack(rows))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
