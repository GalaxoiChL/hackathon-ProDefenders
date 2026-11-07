"""Find ad surfaces (billboards, posters, screens, bus ads) in a video frame, with AI. No clicking.

1. OWLv2 (open-vocabulary detector): finds boxes for text prompts like "a billboard"
2. SAM 2 (segmentation): cuts out the exact surface inside each box
3. the mask is simplified to a 4-corner quad (TL, TR, BR, BL) the insertion engine can use

    python pipeline/detect_surfaces.py assets/clips/melbourne.mp4
    -> assets/clips/melbourne.surfaces.json  +  assets/clips/melbourne.surfaces.jpg (preview)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

# prompt -> surface type written to surfaces.json
PROMPTS = {
    "a billboard": "billboard",
    "an advertising poster on a wall": "poster",
    "a digital advertising screen": "screen",
    "an advertisement on the side of a bus": "vehicle",
}
OWL_MODEL = "google/owlv2-base-patch16-ensemble"
SAM_WEIGHTS = "sam2.1_t.pt"


def read_frame(video: Path, idx: int) -> np.ndarray:
    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit(f"cannot read frame {idx} of {video}")
    return frame


def detect_boxes(frame: np.ndarray, prompts: list[str], threshold: float):
    """Open-vocabulary detection. Returns [(x1, y1, x2, y2), score, prompt]."""
    import torch
    from PIL import Image
    from transformers import Owlv2ForObjectDetection, Owlv2Processor

    processor = Owlv2Processor.from_pretrained(OWL_MODEL)
    model = Owlv2ForObjectDetection.from_pretrained(OWL_MODEL).eval()
    image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    inputs = processor(text=[prompts], images=image, return_tensors="pt")
    with torch.no_grad():
        outputs = model(**inputs)
    # OWLv2 pads the image to a square (bottom/right), so boxes are relative to that square
    side = max(frame.shape[:2])
    target = torch.tensor([[side, side]])
    if hasattr(processor, "post_process_grounded_object_detection"):
        res = processor.post_process_grounded_object_detection(
            outputs=outputs, threshold=threshold, target_sizes=target, text_labels=[prompts])[0]
    else:
        res = processor.post_process_object_detection(outputs=outputs, threshold=threshold, target_sizes=target)[0]
    out = []
    for box, score, label in zip(res["boxes"].tolist(), res["scores"].tolist(), res["labels"].tolist()):
        out.append((box, float(score), prompts[int(label)]))
    return out


def nms(dets, iou: float = 0.4):
    if not dets:
        return []
    boxes = [[b[0], b[1], b[2] - b[0], b[3] - b[1]] for b, _, _ in dets]
    scores = [s for _, s, _ in dets]
    keep = cv2.dnn.NMSBoxes(boxes, scores, 0.0, iou)
    return [dets[i] for i in np.array(keep).reshape(-1)]


def order_corners(pts: np.ndarray) -> np.ndarray:
    """TL, TR, BR, BL."""
    pts = pts.reshape(4, 2).astype(np.float32)
    s, d = pts.sum(axis=1), np.diff(pts, axis=1).reshape(-1)
    return np.float32([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]])


def mask_to_quad(mask: np.ndarray) -> np.ndarray | None:
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    hull = cv2.convexHull(max(contours, key=cv2.contourArea))
    peri = cv2.arcLength(hull, True)
    for eps in np.linspace(0.01, 0.12, 23):
        approx = cv2.approxPolyDP(hull, eps * peri, True)
        if len(approx) == 4:
            return order_corners(approx)
    return order_corners(cv2.boxPoints(cv2.minAreaRect(hull)))  # fallback: rotated rectangle


def _line_intersection(p1, d1, p2, d2) -> np.ndarray:
    """Intersection of lines p1 + t*d1 and p2 + s*d2."""
    a = np.array([[d1[0], -d2[0]], [d1[1], -d2[1]]], np.float64)
    if abs(np.linalg.det(a)) < 1e-9:
        return (p1 + p2) / 2
    t, _ = np.linalg.solve(a, p2 - p1)
    return p1 + t * d1


def snap_quad_to_frame(gray: np.ndarray, quad: np.ndarray, max_frac: float = 0.08) -> np.ndarray:
    """Push each side of the quad outward to the billboard's OUTER edge.

    SAM tends to cut out the printed picture and miss a light frame/border around it (it blends
    with a light wall), which left a strip of the old billboard visible after insertion. For each
    side we slide a parallel line outward and measure the image gradient along it; the outermost
    strong edge within `max_frac` of the billboard size is the frame's outer edge.
    """
    grad = cv2.magnitude(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
    h, w = gray.shape
    center = quad.mean(axis=0)
    size = max(np.ptp(quad[:, 0]), np.ptp(quad[:, 1]))
    max_d = max(3, int(size * max_frac))
    lines = []
    for i in range(4):
        a, b = quad[i].astype(np.float64), quad[(i + 1) % 4].astype(np.float64)
        d = b - a
        n = np.array([-d[1], d[0]]) / (np.linalg.norm(d) + 1e-9)
        if np.dot((a + b) / 2 - center, n) < 0:
            n = -n  # make the normal point outward
        ts = np.linspace(0.15, 0.85, 40)[:, None]
        base = a + ts * d
        scores = []
        for off in range(0, max_d + 1):
            pts = np.round(base + off * n).astype(int)
            ok = (pts[:, 0] >= 0) & (pts[:, 0] < w) & (pts[:, 1] >= 0) & (pts[:, 1] < h)
            scores.append(float(grad[pts[ok, 1], pts[ok, 0]].mean()) if ok.any() else 0.0)
        scores = np.array(scores)
        strong = np.nonzero(scores >= 0.6 * scores.max())[0] if scores.max() > 0 else [0]
        lines.append((a + int(strong[-1]) * n, d))  # outermost strong edge
    return np.float32([_line_intersection(*lines[(i - 1) % 4], *lines[i]) for i in range(4)])


def quad_from_box(box) -> np.ndarray:
    x1, y1, x2, y2 = box
    return np.float32([[x1, y1], [x2, y1], [x2, y2], [x1, y2]])


def quad_aspect(q: np.ndarray) -> float:
    w = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / 2
    h = (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1])) / 2
    return float(w / max(h, 1e-6))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("--frame", type=int, default=0)
    # 0.3: on the Melbourne clip everything above was a real ad surface, everything below was noise
    ap.add_argument("--threshold", type=float, default=0.3)
    ap.add_argument("--min-area", type=float, default=0.002, help="min surface area as a fraction of the frame")
    ap.add_argument("--max-area", type=float, default=0.4)
    ap.add_argument("--no-sam", action="store_true", help="use detector boxes as quads (faster, less exact)")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    out = args.out or args.video.with_suffix(".surfaces.json")

    frame = read_frame(args.video, args.frame)
    h, w = frame.shape[:2]
    prompts = list(PROMPTS)
    dets = nms(detect_boxes(frame, prompts, args.threshold))
    dets = [d for d in dets if args.min_area <= (d[0][2] - d[0][0]) * (d[0][3] - d[0][1]) / (w * h) <= args.max_area]
    print(f"detector: {len(dets)} candidate surfaces")

    sam = None
    if not args.no_sam and dets:
        from ultralytics import SAM
        sam = SAM(SAM_WEIGHTS)

    surfaces = []
    preview = frame.copy()
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    for i, (box, score, prompt) in enumerate(sorted(dets, key=lambda d: -d[1]), start=1):
        box = [max(0, box[0]), max(0, box[1]), min(w - 1, box[2]), min(h - 1, box[3])]
        quad, method = None, "box"
        if sam is not None:
            res = sam.predict(frame, bboxes=[box], verbose=False)[0]
            if res.masks is not None and len(res.masks.data):
                m = res.masks.data[0].cpu().numpy() > 0.5
                if m.shape != (h, w):
                    m = cv2.resize(m.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST) > 0
                q = mask_to_quad(m)
                # trust SAM only if its quad roughly fills the detector box
                if q is not None and cv2.contourArea(q) > 0.5 * (box[2] - box[0]) * (box[3] - box[1]):
                    quad, method = snap_quad_to_frame(gray, q), "sam+snap"
        if quad is None:
            quad = quad_from_box(box)
        sid = f"s{i}"
        surfaces.append({
            "id": sid, "type": PROMPTS[prompt], "frame": args.frame,
            "corners": np.round(quad, 1).tolist(), "aspect": round(quad_aspect(quad), 3),
            "confidence": round(score, 3), "method": method,
        })
        cv2.polylines(preview, [quad.astype(np.int32)], True, (0, 255, 0), 3, cv2.LINE_AA)
        label = f"{sid} {PROMPTS[prompt]} {score:.2f}"
        org = (int(quad[0][0]), max(25, int(quad[0][1]) - 10))
        cv2.putText(preview, label, org, cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 5, cv2.LINE_AA)
        cv2.putText(preview, label, org, cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2, cv2.LINE_AA)
        print(f"  {sid}: {PROMPTS[prompt]:8s} conf {score:.2f}  aspect {quad_aspect(quad):.2f}  via {method}")

    out.write_text(json.dumps({"clip": args.video.stem, "surfaces": surfaces}, indent=2), encoding="utf-8")
    preview_path = out.with_suffix(".jpg")
    cv2.imwrite(str(preview_path), preview)
    print(f"wrote {out}\nwrote {preview_path}")


if __name__ == "__main__":
    main()
