"""AI format adaptation ("generative expand"): extend a real ad's background to the surface's format.

The ad is placed (whole, undistorted) on a canvas with the surface's aspect ratio; an image model
fills ONLY the empty bands around it with a natural continuation of the ad's background. Finally
the original ad is pasted back exactly over the middle, so the brand's text, price and logo are
guaranteed unchanged (the model only ever creates the extra background).

Providers:
  local  (default) fully on this laptop: gemma3 (Ollama) describes the ad's background, then
         Stable Diffusion inpainting on the GPU paints the bands. Free, private, works offline.
  gemini Google Gemini image API (needs GEMINI_API_KEY in .env with billing / prepaid credits).

    python pipeline/gen_extend.py data/creatives/ro-pizza-hut.jpg --aspect 0.78 --out assets/generated/melbourne/ro.png
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


# ---------- local provider: gemma3 describes, Stable Diffusion paints ----------
SD_MODEL = "stable-diffusion-v1-5/stable-diffusion-inpainting"
NEGATIVE = ("text, letters, words, numbers, typography, writing, caption, japanese text, kanji, characters, "
            "logo, watermark, signature, frame, border, blurry, low quality, distorted, deformed")
SEEDS = (7, 21, 42)  # several tries, keep the one whose new areas look least like fake text
_sd_pipe = None


def describe_background(ad: np.ndarray) -> str:
    """Ask the local vision model what the ad's background looks like, as an image-generation prompt."""
    import urllib.request as ur
    small = cv2.resize(ad, None, fx=min(1.0, 640 / max(ad.shape[:2])), fy=min(1.0, 640 / max(ad.shape[:2])))
    body = {
        "model": "gemma3:4b", "stream": False, "options": {"temperature": 0.2},
        "prompt": ("Describe ONLY the background of this advertisement as a short prompt for an image "
                   "generator: colors, lighting, textures and the kind of objects scattered on it. "
                   "Ignore and do not mention any text, prices or logos. One line, max 30 words, English."),
        "images": [base64.b64encode(cv2.imencode(".jpg", small)[1].tobytes()).decode()],
    }
    try:
        req = ur.Request("http://localhost:11434/api/generate", data=json.dumps(body).encode(),
                         headers={"Content-Type": "application/json"})
        with ur.urlopen(req, timeout=120) as r:
            text = json.loads(r.read())["response"].strip().strip('"')
        return text.splitlines()[0][:300]
    except Exception:  # Ollama not running: a neutral prompt still gives a matching texture
        return "seamless continuation of the same advertising background, same colors and lighting"


def generate_local(canvas: np.ndarray, rect, prompt: str, steps: int = 30, seed: int = 7) -> np.ndarray:
    """Stable Diffusion inpainting of everything outside `rect` (the bands around the ad)."""
    global _sd_pipe
    import torch
    from diffusers import StableDiffusionInpaintPipeline
    from PIL import Image

    if not torch.cuda.is_available():
        raise RuntimeError("Stable Diffusion needs the CUDA build of PyTorch (GPU)")
    if _sd_pipe is None:
        # the repo only ships fp16 weights (*.fp16.safetensors); the safety checker (608 MB) is not
        # downloaded: we only paint plain backgrounds around a brand's own ad
        _sd_pipe = StableDiffusionInpaintPipeline.from_pretrained(
            SD_MODEL, torch_dtype=torch.float16, variant="fp16",
            safety_checker=None, requires_safety_checker=False,
        ).to("cuda")
        _sd_pipe.enable_attention_slicing()  # fits comfortably in 6 GB of VRAM
        _sd_pipe.set_progress_bar_config(disable=True)
    ch, cw = canvas.shape[:2]
    # SD 1.5 works best around 512-768 px with sides divisible by 8
    s = 768 / max(cw, ch)
    W, H = int(round(cw * s / 8) * 8), int(round(ch * s / 8) * 8)
    x, y, nw, nh = rect
    mask = np.full((ch, cw), 255, np.uint8)
    overlap = max(4, min(nw, nh) // 40)  # let the model repaint a thin rim of the ad so the seam blends
    mask[y + overlap:y + nh - overlap, x + overlap:x + nw - overlap] = 0
    img = Image.fromarray(cv2.cvtColor(cv2.resize(canvas, (W, H), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB))
    small_mask = cv2.resize(mask, (W, H), interpolation=cv2.INTER_NEAREST)
    msk = Image.fromarray(small_mask)
    band = cv2.erode(small_mask, np.ones((9, 9), np.uint8)) > 0  # new areas only, away from the seam
    candidates = []
    for s in ((seed,) + tuple(x for x in SEEDS if x != seed)):
        result = _sd_pipe(
            prompt=f"{prompt}, clean background, no text, professional advertising poster, high quality",
            negative_prompt=NEGATIVE, image=img, mask_image=msk, width=W, height=H,
            num_inference_steps=steps, guidance_scale=8.0,
            generator=torch.Generator("cuda").manual_seed(s),
        ).images[0]
        out = cv2.cvtColor(np.array(result), cv2.COLOR_RGB2BGR)
        # fake text = dense, fine, high-contrast strokes: measure fine detail in the new areas
        gray = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY).astype(np.float32)
        score = float(np.abs(cv2.Laplacian(gray, cv2.CV_32F))[band].mean()) if band.any() else 0.0
        candidates.append((score, out))
    return [out for _, out in sorted(candidates, key=lambda c: c[0])]  # cleanest first


def bands_of(img: np.ndarray, rect, canvas_shape) -> list[np.ndarray]:
    """The newly generated areas (above/below or left/right of the ad), in the image's own scale."""
    ch, cw = canvas_shape[:2]
    sy, sx = img.shape[0] / ch, img.shape[1] / cw
    x, y, nw, nh = rect
    y0, y1, x0, x1 = int(y * sy), int((y + nh) * sy), int(x * sx), int((x + nw) * sx)
    parts = [img[:y0], img[y1:], img[:, :x0], img[:, x1:]]
    return [p for p in parts if p.shape[0] >= 16 and p.shape[1] >= 16]


def colors_match(gen: np.ndarray, rect, canvas_shape, max_delta: float = 22.0) -> bool:
    """Quality gate: the new areas must continue the ad's own palette. Compares the average Lab color
    of each generated band with the strip of the ad it touches (a psychedelic multicolor band next to
    a flat red ad fails)."""
    ch, cw = canvas_shape[:2]
    img = cv2.resize(gen, (cw, ch), interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
    x, y, nw, nh = rect
    sh, sw = max(4, nh // 10), max(4, nw // 10)
    pairs = []
    if y > 8:
        pairs += [(lab[:y], lab[y:y + sh, x:x + nw]), (lab[y + nh:], lab[y + nh - sh:y + nh, x:x + nw])]
    if x > 8:
        pairs += [(lab[:, :x], lab[y:y + nh, x:x + sw]), (lab[:, x + nw:], lab[y:y + nh, x + nw - sw:x + nw])]
    for band, edge in pairs:
        if band.size == 0 or edge.size == 0:
            continue
        b, e = band.reshape(-1, 3), edge.reshape(-1, 3)
        delta = float(np.linalg.norm(b.mean(axis=0) - e.mean(axis=0)))
        # also reject a band far more colorful/varied than the ad's edge
        if delta > max_delta or b[:, 1:].std() > 2.0 * e[:, 1:].std() + 10:
            return False
    return True


def has_fake_text(parts: list[np.ndarray]) -> bool:
    """Quality gate by the local vision model: does any generated area contain text-like marks?"""
    import urllib.request as ur
    for p in parts:
        body = {
            "model": "gemma3:4b", "stream": False, "options": {"temperature": 0},
            "prompt": ("Look at this image strip. Does it contain any text, letters, characters, numbers, "
                       "or scribbles that look like writing (even unreadable)? Answer only YES or NO."),
            "images": [base64.b64encode(cv2.imencode(".jpg", p)[1].tobytes()).decode()],
        }
        try:
            req = ur.Request("http://localhost:11434/api/generate", data=json.dumps(body).encode(),
                             headers={"Content-Type": "application/json"})
            with ur.urlopen(req, timeout=120) as r:
                if json.loads(r.read())["response"].strip().upper().startswith("YES"):
                    return True
        except Exception:
            return False  # checker unavailable: do not block (the edge-detail ranking still applies)
    return False


def adapt(ad: np.ndarray, aspect: float, provider: str = "local") -> tuple[np.ndarray, str]:
    """Whole pipeline for one ad: canvas -> AI fill -> original pasted back. Returns image + description."""
    if provider == "gemini":
        ratio = closest_ratio(aspect)
        canvas, rect = placed_canvas(ad, RATIOS[ratio])
        gen, model = generate(canvas, ratio, api_key())
        return paste_original(gen, ad, rect, canvas.shape), model
    canvas, rect = placed_canvas(ad, aspect)
    prompt = describe_background(ad)
    for i, gen in enumerate(generate_local(canvas, rect, prompt)):
        if not colors_match(gen, rect, canvas.shape):
            continue
        if not has_fake_text(bands_of(gen, rect, canvas.shape)):
            return paste_original(gen, ad, rect, canvas.shape), f"local SD inpainting (try {i + 1}); prompt: {prompt}"
    raise RuntimeError("no AI expansion passed the quality checks (palette, no fake text); use the smart crop")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", type=Path)
    ap.add_argument("--aspect", type=float, required=True, help="surface width / height")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--provider", choices=["local", "gemini"], default="local")
    args = ap.parse_args()

    ad = cv2.imread(str(args.image), cv2.IMREAD_COLOR)
    if ad is None:
        raise SystemExit(f"cannot read {args.image}")
    t0 = time.time()
    out, how = adapt(ad, args.aspect, args.provider)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(args.out), out)
    print(f"wrote {args.out}  ({time.time() - t0:.1f}s, {how})")


if __name__ == "__main__":
    main()
