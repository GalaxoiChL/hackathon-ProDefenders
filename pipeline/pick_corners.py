"""Click the 4 corners of the billboard on a video frame and save them as JSON.

Click order: top-left, top-right, bottom-right, bottom-left.
Keys: r = reset, Enter/s = save, q/Esc = quit without saving.

    python pipeline/pick_corners.py assets/clips/street.mp4            # -> assets/clips/street.corners.json
    python pipeline/pick_corners.py assets/clips/street.mp4 --frame 0
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2

LABELS = ["TL", "TR", "BR", "BL"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--frame", type=int, default=0)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--max-width", type=int, default=1400, help="display size; saved corners are full-res")
    args = ap.parse_args()
    out = args.out or args.video.with_suffix(".corners.json")

    cap = cv2.VideoCapture(str(args.video))
    cap.set(cv2.CAP_PROP_POS_FRAMES, args.frame)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit(f"cannot read frame {args.frame} of {args.video}")

    scale = min(1.0, args.max_width / frame.shape[1])
    shown = cv2.resize(frame, None, fx=scale, fy=scale) if scale < 1 else frame.copy()
    pts: list[tuple[float, float]] = []

    def redraw():
        img = shown.copy()
        for i, (x, y) in enumerate(pts):
            p = (int(x * scale), int(y * scale))
            cv2.circle(img, p, 5, (0, 255, 255), -1)
            cv2.putText(img, LABELS[i], (p[0] + 8, p[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        if len(pts) > 1:
            poly = [(int(x * scale), int(y * scale)) for x, y in pts]
            for a, b in zip(poly, poly[1:] + ([poly[0]] if len(pts) == 4 else [])):
                cv2.line(img, a, b, (0, 255, 0), 2)
        hint = f"click {LABELS[len(pts)]}" if len(pts) < 4 else "Enter = save, r = reset"
        cv2.putText(img, hint, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.imshow("pick corners", img)

    def on_mouse(event, x, y, *_):
        if event == cv2.EVENT_LBUTTONDOWN and len(pts) < 4:
            pts.append((x / scale, y / scale))
            redraw()

    cv2.namedWindow("pick corners")
    cv2.setMouseCallback("pick corners", on_mouse)
    redraw()
    while True:
        key = cv2.waitKey(30) & 0xFF
        if key in (ord("r"),):
            pts.clear()
            redraw()
        elif key in (13, ord("s")) and len(pts) == 4:
            out.write_text(json.dumps({"frame": args.frame, "corners": [[round(x, 1), round(y, 1)] for x, y in pts]}, indent=2))
            print(f"saved {out}")
            break
        elif key in (27, ord("q")):
            print("quit without saving")
            break
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
