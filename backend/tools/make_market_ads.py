"""Placeholder ad images for every demo market, drawn from the sample ads (brand, headline, price, colors).

    python backend/tools/make_market_ads.py            # only markets without an image yet
    python backend/tools/make_market_ads.py --force    # redraw all (also overwrites ro/us/jp)

Writes assets/ads/<cc>.png (landscape 1200x600) and assets/ads/<cc>_portrait.png (600x800), the
same layout as pipeline/make_test_ads.py. Real creatives from task 2 (assets/generated/) always win.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]          # backend/ (data root)
sys.path.insert(0, str(ROOT.parent))               # repo root, so `import backend` works

from backend.config import DEFAULT_MARKETS  # noqa: E402
from backend.store import SAMPLE_ADS  # noqa: E402

OUT = ROOT / "assets" / "ads"


def rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    names = ["arialbd.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf"] if bold else \
            ["arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def fit(d: ImageDraw.ImageDraw, text: str, max_w: int, size: int, bold: bool = True):
    """Largest font <= size that fits `text` in max_w pixels."""
    while size > 12:
        f = font(size, bold)
        if d.textlength(text, font=f) <= max_w:
            return f
        size -= 4
    return font(12, bold)


def spec(ad: dict) -> dict:
    c = ad["colors"]
    return dict(bg=rgb(c["bg"]), fg=rgb(c["fg"]), accent=rgb(c["accent"]),
                title=ad["brand"].upper(), sub=ad["headline"], tag=ad["price"])


def landscape(s: dict, w: int = 1200, h: int = 600) -> Image.Image:
    img = Image.new("RGB", (w, h), s["bg"])
    d = ImageDraw.Draw(img)
    d.rectangle([0, h - 70, w, h], fill=s["accent"])
    d.text((60, 90), s["title"], font=fit(d, s["title"], w - 120, 130), fill=s["fg"])
    d.text((64, 260), s["sub"], font=fit(d, s["sub"], w - 128, 52, bold=False), fill=s["fg"])
    d.ellipse([w - 330, 300, w - 60, 570], fill=s["accent"])
    tf = fit(d, s["tag"], 230, 80)
    tw = d.textlength(s["tag"], font=tf)
    d.text((w - 195 - tw / 2, 390), s["tag"], font=tf, fill=s["bg"])
    return img


def portrait(s: dict, w: int = 600, h: int = 800) -> Image.Image:
    img = Image.new("RGB", (w, h), s["bg"])
    d = ImageDraw.Draw(img)
    d.rectangle([0, h - 60, w, h], fill=s["accent"])
    r = 150
    cx, cy = w // 2, h - 60 - r - 40
    top, bottom = 60, cy - r - 25          # title + subtitle must stay above the price circle
    sf = fit(d, s["sub"], w - 60, 34, bold=False)
    sub_h = sf.size + 20
    size = 110
    while True:  # biggest title font whose greedy line-wrap fits width and height
        tf = font(size)
        lines: list[str] = []
        for word in s["title"].split():
            trial = f"{lines[-1]} {word}" if lines else word
            if lines and d.textlength(trial, font=tf) <= w - 60:
                lines[-1] = trial
            else:
                lines.append(word)
        line_h = int(size * 1.12)
        fits_w = all(d.textlength(ln, font=tf) <= w - 60 for ln in lines)
        if (fits_w and top + len(lines) * line_h + sub_h <= bottom) or size <= 24:
            break
        size -= 4
    y = top + (bottom - top - len(lines) * line_h - sub_h) // 2  # center the text block
    for ln in lines:
        tw = d.textlength(ln, font=tf)
        d.text(((w - tw) / 2, y), ln, font=tf, fill=s["fg"])
        y += line_h
    tw = d.textlength(s["sub"], font=sf)
    d.text(((w - tw) / 2, y + 16), s["sub"], font=sf, fill=s["fg"])
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=s["accent"])
    pf = fit(d, s["tag"], 2 * r - 40, 90)
    tw = d.textlength(s["tag"], font=pf)
    d.text((cx - tw / 2, cy - pf.size * 0.6), s["tag"], font=pf, fill=s["bg"])
    return img


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="redraw images that already exist")
    ap.add_argument("--markets", nargs="+", default=list(DEFAULT_MARKETS))
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    by_region = {}
    for ad in SAMPLE_ADS:
        by_region.setdefault(ad["region"], ad)
    for cc in (m.upper() for m in args.markets):
        ad = by_region.get(cc)
        if not ad:
            print(f"skip {cc}: no sample ad")
            continue
        s = spec(ad)
        for path, draw in ((OUT / f"{cc.lower()}.png", landscape), (OUT / f"{cc.lower()}_portrait.png", portrait)):
            if path.exists() and not args.force:
                continue
            draw(s).save(path)
            print(f"wrote {path.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
