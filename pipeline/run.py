"""One command, whole pipeline: clip -> AI surface detection -> ad per country -> rendered videos -> manifest.

    python pipeline/run.py assets/clips/melbourne.mp4 --max-frames 480
    -> output/melbourne_ro.mp4, _us.mp4, _jp.mp4, _ai_view.mp4, _compare.mp4
    -> output/melbourne.manifest.json   (what the frontend reads)

Plugs in the other tasks' outputs when they exist, and falls back safely when they don't:
  - data/ads.json                          (task 4) brands + real creatives per region
  - output/<clip>.scene.json               (task 2) AI choice of ad per region, with reason
  - assets/generated/<clip>/<region>.png   (task 2) AI-adapted creative for the surface format
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adapt_ad import fit_to_aspect  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
LABELS = {"RO": "România", "US": "SUA", "JP": "Japonia", "DE": "Germania", "FR": "Franța", "IT": "Italia", "GB": "Marea Britanie"}


def ascii_label(text: str) -> str:
    """OpenCV's built-in fonts are ASCII-only: 'ROMÂNIA' would render as 'ROM??NIA'."""
    import unicodedata

    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def rel(p: Path) -> str:
    """Repo-relative path with forward slashes (what the manifest and the frontend use)."""
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def run(cmd: list[str]) -> None:
    print("$", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, cwd=ROOT)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def choose_ad(region: str, ads: list[dict] | None, scene: dict | None) -> tuple[dict | None, str]:
    """Which ad for this region, and why. Task 2's AI choice wins; otherwise first ad of the region."""
    by_id = {a["id"]: a for a in ads or []}
    choice = ((scene or {}).get("choices") or {}).get(region)
    if choice and choice.get("ad_id") in by_id:
        return by_id[choice["ad_id"]], choice.get("reason", "ales de AI")
    for ad in ads or []:
        if ad.get("region") == region:
            return ad, "implicit: primul brand pentru regiune din data/ads.json (analiza AI a scenei lipsește)"
    return None, "nu există reclame pentru regiune în data/ads.json"


def creative_for(region: str, ad: dict | None, clip: str, aspect: float, work: Path) -> Path:
    """Path of the image to paste for this region, already at the surface's aspect ratio."""
    generated = ROOT / "assets" / "generated" / clip / f"{region.lower()}.png"
    if generated.exists():  # task 2 produced an AI-adapted creative
        return generated
    if not ad or not ad.get("creative"):
        raise SystemExit(f"no real ad for {region} in data/ads.json")
    src = ROOT / ad["creative"]
    if not src.exists():
        raise SystemExit(f"missing {ad['creative']} for {region}: download it from {ad.get('creative_source', '?')}")
    img = cv2.imread(str(src), cv2.IMREAD_COLOR)
    if img is None:
        raise SystemExit(f"cannot read creative {src}")
    out = work / f"{region.lower()}.png"
    cv2.imwrite(str(out), fit_to_aspect(img, aspect))  # safe fallback: fit without distortion
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("--regions", nargs="+", help="default: every region that has an ad in data/ads.json")
    ap.add_argument("--surface", help="surface id to use (default: most confident)")
    ap.add_argument("--redetect", action="store_true", help="run detection even if surfaces.json exists")
    ap.add_argument("--max-frames", type=int, default=0)
    ap.add_argument("--no-compare", action="store_true", help="skip the side-by-side video")
    args = ap.parse_args()

    video = args.video if args.video.is_absolute() else (ROOT / args.video)
    clip = video.stem
    out_dir = ROOT / "output"
    out_dir.mkdir(exist_ok=True)
    ads = load_json(ROOT / "data" / "ads.json")
    if not ads:
        raise SystemExit("data/ads.json is missing or empty: add real ads (see CLAUDE.md)")
    regions = [r.upper() for r in args.regions] if args.regions \
        else list(dict.fromkeys(a["region"] for a in ads))

    # 1. AI: where can ads go?
    surfaces_path = out_dir / f"{clip}.surfaces.json"
    if args.redetect or not surfaces_path.exists():
        run([PY, "pipeline/detect_surfaces.py", video, "--out", surfaces_path])
    surfaces = load_json(surfaces_path)["surfaces"]
    if not surfaces:
        raise SystemExit("the detector found no ad surfaces in this clip")
    surface = next((s for s in surfaces if s["id"] == args.surface), None) if args.surface \
        else max(surfaces, key=lambda s: s["confidence"])
    if surface is None:
        raise SystemExit(f"no surface {args.surface!r}; have {[s['id'] for s in surfaces]}")
    print(f"surface {surface['id']}: {surface['type']}, aspect {surface['aspect']}, confidence {surface['confidence']}")

    # 2. which ad per region (task 2 AI choice if present) and its creative at the surface format
    scene = load_json(out_dir / f"{clip}.scene.json")
    work = out_dir / f"{clip}_creatives"
    work.mkdir(exist_ok=True)
    picks = {}
    for region in regions:
        ad, reason = choose_ad(region, ads, scene)
        picks[region] = (ad, reason, creative_for(region, ad, clip, surface["aspect"], work))
        print(f"  {region}: {(ad or {}).get('brand')}  ({reason})")

    # 3. render every region in one pass + the "AI view"
    cmd = [PY, "pipeline/insert_ad.py", video, "--corners", surfaces_path, "--surface", surface["id"],
           "--out", out_dir / clip, "--track", "--occlude", "--debug"]
    for region, (_, _, creative) in picks.items():
        cmd += ["--ad", f"{region.lower()}={creative}"]
    if args.max_frames:
        cmd += ["--max-frames", str(args.max_frames)]
    run(cmd)

    compare = out_dir / f"{clip}_compare.mp4"
    if not args.no_compare:
        run([PY, "pipeline/side_by_side.py", out_dir / clip, "--versions", *[r.lower() for r in regions],
             "--labels", *[ascii_label(LABELS.get(r, r)).upper() for r in regions], "--height", "540", "--out", compare])

    # 4. manifest for the frontend (contract in CLAUDE.md)
    manifest = {
        "clip": clip,
        "source": rel(video),
        "ai_view": rel(out_dir / f"{clip}_ai_view.mp4"),
        "compare": rel(compare) if compare.exists() else None,
        "surface": surface,
        "surfaces": surfaces,
        "scene": {k: v for k, v in (scene or {}).items() if k != "choices"} or None,
        "regions": [
            {"code": r, "label": LABELS.get(r, r), "video": rel(out_dir / f"{clip}_{r.lower()}.mp4"),
             "ad_id": (ad or {}).get("id"), "brand": (ad or {}).get("brand"),
             "creative": rel(creative), "reason": reason}
            for r, (ad, reason, creative) in picks.items()
        ],
    }
    manifest_path = out_dir / f"{clip}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {rel(manifest_path)}")


if __name__ == "__main__":
    main()
