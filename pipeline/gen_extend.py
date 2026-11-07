"""AI format adaptation: extend a real ad's background to the surface's format, keeping the ad intact.

The ad is placed (whole, undistorted) on a canvas with the surface's aspect ratio. Gemini fills
ONLY the empty bands around it with a natural continuation of the ad's background. Finally the
original ad is pasted back exactly over the middle, so the brand's text, price and logo are
guaranteed unchanged (the model only ever creates the extra background).

    python pipeline/gen_extend.py data/creatives/ro-pizza-hut.jpg --aspect 0.78 --out assets/generated/melbourne/ro.png

Needs GEMINI_API_KEY in .env. The key is read from the file and never printed.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adapt_ad import blurred_fill  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MODELS = ["gemini-2.5-flash-image", "gemini-3.1-flash-image"]  # tried in order
# Gemini's supported output ratios (width:height)
RATIOS = {"1:1": 1.0, "2:3": 2 / 3, "3:2": 1.5, "3:4": 0.75, "4:3": 4 / 3, "4:5": 0.8, "5:4": 1.25,
          "9:16": 9 / 16, "16:9": 16 / 9, "21:9": 21 / 9}

PROMPT = (
    "This is an outdoor advertisement placed in the middle of a taller/wider canvas. The areas around it are "
    "a blurred placeholder. Replace ONLY those blurred areas with a seamless, natural continuation of the "
    "advertisement's own background and visual style (same colors, lighting, textures and kind of objects), "
    "so the whole canvas looks like one professionally designed poster in this format. "
    "Do not change, move, redraw or cover anything inside the original advertisement. "
    "Do not add any text, letters, numbers, logos or watermarks in the new areas."
)


def api_key() -> str:
    env = ROOT / ".env"
    for line in env.read_text(encoding="utf-8").splitlines() if env.exists() else []:
        if line.startswith("GEMINI_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("GEMINI_API_KEY missing in .env")


def closest_ratio(aspect: float) -> str:
    return min(RATIOS, key=lambda k: abs(np.log(RATIOS[k] / aspect)))


def placed_canvas(ad: np.ndarray, aspect: float, long_side: int = 1024):
    """Canvas at `aspect` with the whole ad centered; returns canvas and the ad's rectangle on it."""
    cw, ch = (long_side, round(long_side / aspect)) if aspect >= 1 else (round(long_side * aspect), long_side)
    canvas = blurred_fill(ad, cw, ch)
    h, w = ad.shape[:2]
    s = min(cw / w, ch / h)
    nw, nh = round(w * s), round(h * s)
    x, y = (cw - nw) // 2, (ch - nh) // 2
    canvas[y:y + nh, x:x + nw] = cv2.resize(ad, (nw, nh), interpolation=cv2.INTER_AREA)
    return canvas, (x, y, nw, nh)


def generate(canvas: np.ndarray, ratio: str, key: str) -> tuple[np.ndarray, str]:
    data = base64.b64encode(cv2.imencode(".png", canvas)[1].tobytes()).decode()
    body = {
        "contents": [{"parts": [{"text": PROMPT}, {"inline_data": {"mime_type": "image/png", "data": data}}]}],
        "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": ratio}},
    }
    errors = []
    for model in MODELS:
        req = urllib.request.Request(API.format(model=model), data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "x-goog-api-key": key})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                resp = json.loads(r.read())
        except urllib.error.HTTPError as e:
            errors.append(f"{model}: HTTP {e.code} {e.read().decode(errors='replace')[:300]}")
            continue
        for cand in resp.get("candidates", []):
            for part in cand.get("content", {}).get("parts", []):
                inline = part.get("inlineData") or part.get("inline_data")
                if inline:
                    img = cv2.imdecode(np.frombuffer(base64.b64decode(inline["data"]), np.uint8), cv2.IMREAD_COLOR)
                    return img, model
        errors.append(f"{model}: no image in response {json.dumps(resp)[:300]}")
    raise RuntimeError("image generation failed:\n" + "\n".join(errors))


def paste_original(gen: np.ndarray, ad: np.ndarray, rect, canvas_shape) -> np.ndarray:
    """Resize the generated image to the canvas size and put the untouched ad back on top,
    with a short feather so the seam is invisible."""
    ch, cw = canvas_shape[:2]
    out = cv2.resize(gen, (cw, ch), interpolation=cv2.INTER_CUBIC)
    x, y, nw, nh = rect
    patch = cv2.resize(ad, (nw, nh), interpolation=cv2.INTER_AREA).astype(np.float32)
    feather = max(2, min(nw, nh) // 60)
    a = np.ones((nh, nw), np.float32)
    ramp = np.linspace(0, 1, feather, dtype=np.float32)
    if y > 0:
        a[:feather] *= ramp[:, None]
        a[-feather:] *= ramp[::-1][:, None]
    if x > 0:
        a[:, :feather] *= ramp[None, :]
        a[:, -feather:] *= ramp[::-1][None, :]
    region = out[y:y + nh, x:x + nw].astype(np.float32)
    out[y:y + nh, x:x + nw] = (region * (1 - a[..., None]) + patch * a[..., None]).astype(np.uint8)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", type=Path)
    ap.add_argument("--aspect", type=float, required=True, help="surface width / height")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    ad = cv2.imread(str(args.image), cv2.IMREAD_COLOR)
    if ad is None:
        raise SystemExit(f"cannot read {args.image}")
    ratio = closest_ratio(args.aspect)
    canvas, rect = placed_canvas(ad, RATIOS[ratio])
    t0 = time.time()
    gen, model = generate(canvas, ratio, api_key())
    out = paste_original(gen, ad, rect, canvas.shape)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(args.out), out)
    print(f"wrote {args.out}  ({model}, ratio {ratio}, {time.time() - t0:.1f}s)")


if __name__ == "__main__":
    main()
