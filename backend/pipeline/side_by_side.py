"""Stack several rendered versions side by side, synced, with a country label on each.

    python pipeline/side_by_side.py output/melbourne --versions ro us jp \
        --labels "ROMANIA" "USA" "JAPAN" --crop 700 0 1700 1080 --out output/melbourne_compare.mp4
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import cv2
import numpy as np


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("prefix", type=Path)
    ap.add_argument("--versions", nargs="+", default=["ro", "us", "jp"])
    ap.add_argument("--labels", nargs="+")
    ap.add_argument("--crop", nargs=4, type=int, metavar=("X0", "Y0", "X1", "Y1"))
    ap.add_argument("--height", type=int, default=720, help="output height of each panel")
    ap.add_argument("--max-frames", type=int, default=0)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    labels = args.labels or [v.upper() for v in args.versions]

    caps = [cv2.VideoCapture(str(args.prefix.parent / f"{args.prefix.name}_{v}.mp4")) for v in args.versions]
    fps = caps[0].get(cv2.CAP_PROP_FPS) or 30.0
    tmp = args.out.with_suffix(".tmp.mp4")
    writer = None
    n = 0
    while not args.max_frames or n < args.max_frames:
        n += 1
        frames = []
        for cap in caps:
            ok, f = cap.read()
            if not ok:
                break
            frames.append(f)
        if len(frames) != len(caps):
            break
        panels = []
        for f, label in zip(frames, labels):
            if args.crop:
                x0, y0, x1, y1 = args.crop
                f = f[y0:y1, x0:x1]
            s = args.height / f.shape[0]
            f = cv2.resize(f, (int(f.shape[1] * s) // 2 * 2, args.height), interpolation=cv2.INTER_AREA)
            cv2.rectangle(f, (0, 0), (f.shape[1], 56), (0, 0, 0), -1)
            cv2.putText(f, label, (16, 40), cv2.FONT_HERSHEY_DUPLEX, 1.2, (255, 255, 255), 2, cv2.LINE_AA)
            panels.append(f)
        sep = np.full((args.height, 6, 3), 255, np.uint8)
        row = panels[0]
        for p in panels[1:]:
            row = np.hstack([row, sep, p])
        if writer is None:
            writer = cv2.VideoWriter(str(tmp), cv2.VideoWriter_fourcc(*"mp4v"), fps, (row.shape[1], row.shape[0]))
        writer.write(row)
    for cap in caps:
        cap.release()
    if writer is None:
        raise SystemExit("no frames read")
    writer.release()

    import imageio_ffmpeg

    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(tmp),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "21", "-preset", "veryfast",
                    "-movflags", "+faststart", str(args.out)], check=True)
    tmp.unlink(missing_ok=True)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
