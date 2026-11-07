"""Generate placeholder ads (fictional brands) for each region, so we can test without real creatives.

    python pipeline/make_test_ads.py   # -> assets/ads/{ro,us,jp}.png
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "assets" / "ads"
W, H = 1200, 600

ADS = {
    "ro": dict(bg=(200, 30, 35), fg=(255, 255, 255), accent=(255, 200, 0),
               title="PIZZA BUNICII", sub="Felia caldă, la tine în cartier", tag="19 LEI"),
    "us": dict(bg=(20, 40, 90), fg=(255, 255, 255), accent=(240, 60, 60),
               title="BURGER BROS", sub="Since 1987 · Open late", tag="$4.99"),
    "jp": dict(bg=(250, 245, 235), fg=(30, 30, 30), accent=(220, 40, 60),
               title="SAKURA RAMEN", sub="Hot bowls, fast. Tokyo style.", tag="¥680"),
}


def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    for name in (["arialbd.ttf", "segoeuib.ttf"] if bold else ["arial.ttf", "segoeui.ttf"]):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make(spec: dict) -> Image.Image:
    img = Image.new("RGB", (W, H), spec["bg"])
    d = ImageDraw.Draw(img)
    d.rectangle([0, H - 70, W, H], fill=spec["accent"])
    d.text((60, 90), spec["title"], font=font(130), fill=spec["fg"])
    d.text((64, 260), spec["sub"], font=font(52, bold=False), fill=spec["fg"])
    d.ellipse([W - 330, 300, W - 60, 570], fill=spec["accent"])
    tag_font = font(80)
    tw = d.textlength(spec["tag"], font=tag_font)
    d.text((W - 195 - tw / 2, 390), spec["tag"], font=tag_font, fill=spec["bg"])
    return img


def make_portrait(spec: dict, pw: int = 600, ph: int = 800) -> Image.Image:
    """Tall layout for portrait billboards (building wraps, bus shelters)."""
    img = Image.new("RGB", (pw, ph), spec["bg"])
    d = ImageDraw.Draw(img)
    d.rectangle([0, ph - 60, pw, ph], fill=spec["accent"])
    words = spec["title"].split()
    title_font = font(110)
    for i, word in enumerate(words):
        tw = d.textlength(word, font=title_font)
        d.text(((pw - tw) / 2, 70 + i * 125), word, font=title_font, fill=spec["fg"])
    sub_font = font(34, bold=False)
    tw = d.textlength(spec["sub"], font=sub_font)
    d.text(((pw - tw) / 2, 70 + len(words) * 125 + 20), spec["sub"], font=sub_font, fill=spec["fg"])
    r = 150
    cx, cy = pw // 2, ph - 60 - r - 40
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=spec["accent"])
    tag_font = font(90)
    tw = d.textlength(spec["tag"], font=tag_font)
    d.text((cx - tw / 2, cy - 55), spec["tag"], font=tag_font, fill=spec["bg"])
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for region, spec in ADS.items():
        for path, img in ((OUT / f"{region}.png", make(spec)), (OUT / f"{region}_portrait.png", make_portrait(spec))):
            img.save(path)
            print(f"wrote {path}")


if __name__ == "__main__":
    main()
