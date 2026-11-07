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
import os
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
    # UTF-8 output for the steps (Windows defaults a piped stdout to cp1252: "ă" crashed analyze_scene)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    subprocess.run([str(c) for c in cmd], check=True, cwd=ROOT, env=env)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def choose_ad(region: str, ads: list[dict] | None, scene: dict | None) -> tuple[dict | None, str]:
    """Which ad for this region, and why. Task 2's AI choice wins; otherwise first ad of the region."""
    by_id = {a["id"]: a for a in ads or []}
    choice = ((scene or {}).get("choices") or {}).get(region)
    if choice and choice.get("ad_id") in by_id:
        return by_id[choice["ad_id"]], choice.get("reason", "ales de AI")
    if choice and choice.get("ad_id") is None:  # AI said: no ad here (brand safety)
        return None, choice.get("reason", "scenă nesigură pentru branduri")
    for ad in ads or []:
        if ad.get("region") == region:
            return ad, "implicit: primul brand pentru regiune din data/ads.json (analiza AI a scenei lipsește)"
    return None, "nu există reclame pentru regiune în data/ads.json"


def creative_for(region: str, ad: dict | None, clip: str, aspect: float, work: Path,
                 ai_adapt: bool = True) -> tuple[Path, str]:
    """Image to paste for this region, already at the surface's aspect ratio, and how it was made.

    1. AI "generative expand" (gen_extend.py, local Stable Diffusion): the WHOLE real ad, with the
       background extended by AI to the surface's format; cached per clip and ad
    2. fallback when the GPU/model is unavailable: smart crop-to-fill (adapt_ad.py)
    """
    if not ad or not ad.get("creative"):
        raise SystemExit(f"no real ad for {region} in data/ads.json")
    src = ROOT / ad["creative"]
    if not src.exists():
        raise SystemExit(f"missing {ad['creative']} for {region}: download it from {ad.get('creative_source', '?')}")
    img = cv2.imread(str(src), cv2.IMREAD_COLOR)
    if img is None:
        raise SystemExit(f"cannot read creative {src}")
    out = work / f"{region.lower()}.png"
    cache = ROOT / "assets" / "generated" / clip / f"{ad['id']}_{aspect:.2f}.png"
    if ai_adapt:
        if not cache.exists():
            try:
                from gen_extend import adapt
                gen, how = adapt(img, aspect, "local")
                cache.parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(cache), gen)
                print(f"  {region}: AI generative expand ({how})")
            except Exception as e:  # no GPU / no model / no internet for the first download
                print(f"  {region}: AI expand unavailable ({type(e).__name__}: {str(e)[:120]}), using smart crop")
        if cache.exists():
            cv2.imwrite(str(out), cv2.imread(str(cache), cv2.IMREAD_COLOR))
            return out, "ai-expand"
    cv2.imwrite(str(out), fit_to_aspect(img, aspect))  # safe fallback: fit without distortion
    return out, "smart-crop"


def main() -> None:
    # Romanian text in the output: keep it printable when stdout is a pipe or a file (cp1252 on Windows)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("--regions", nargs="+", help="default: every region that has an ad in data/ads.json")
    ap.add_argument("--surface", help="surface id to use (default: most confident)")
    ap.add_argument("--redetect", action="store_true", help="run detection even if surfaces.json exists")
    ap.add_argument("--rescene", action="store_true", help="run scene analysis even if scene.json exists")
    ap.add_argument("--no-ai-adapt", action="store_true",
                    help="skip AI generative expand (Stable Diffusion); use the smart crop only")
    ap.add_argument("--max-frames", type=int, default=0)
    ap.add_argument("--no-compare", action="store_true", help="skip the side-by-side video")
    ap.add_argument("--no-publish", action="store_true", help="don't copy the result to frontend/demo/media/")
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
    # 2a. AI: understand the scene, check brand safety, pick the best ad per region (local Ollama)
    scene_path = out_dir / f"{clip}.scene.json"
    if args.rescene or not scene_path.exists():
        try:
            run([PY, "pipeline/analyze_scene.py", video, "--out", scene_path])
        except subprocess.CalledProcessError:
            print("scene analysis failed (is Ollama running?): falling back to the first ad per region")
    scene = load_json(scene_path)
    work = out_dir / f"{clip}_creatives"
    work.mkdir(exist_ok=True)
    picks, methods = {}, {}
    for region in regions:
        ad, reason = choose_ad(region, ads, scene)
        creative, method = creative_for(region, ad, clip, surface["aspect"], work, not args.no_ai_adapt) \
            if ad else (None, None)
        picks[region] = (ad, reason, creative)
        methods[region] = method
        print(f"  {region}: {(ad or {}).get('brand', 'fără reclamă')}  ({reason})")
    placed = [r for r, (ad, _, _) in picks.items() if ad]

    # 3. render every region that gets an ad, in one pass, + the "AI view"
    if placed:
        cmd = [PY, "pipeline/insert_ad.py", video, "--corners", surfaces_path, "--surface", surface["id"],
               "--out", out_dir / clip, "--track", "--occlude", "--occluders", "person,bus,truck,car", "--debug"]
        for region in placed:
            cmd += ["--ad", f"{region.lower()}={picks[region][2]}"]
        if args.max_frames:
            cmd += ["--max-frames", str(args.max_frames)]
        run(cmd)
    else:
        print("no region gets an ad (brand safety): nothing to render")

    compare = out_dir / f"{clip}_compare.mp4"
    if placed and not args.no_compare:
        run([PY, "pipeline/side_by_side.py", out_dir / clip, "--versions", *[r.lower() for r in placed],
             "--labels", *[ascii_label(LABELS.get(r, r)).upper() for r in placed], "--height", "540", "--out", compare])

    # 3b. the original footage cut to the same length, for the frontend's Compare tab
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    if args.max_frames:
        frames = min(frames, args.max_frames)
    original = out_dir / f"{clip}_original.mp4"
    import imageio_ffmpeg
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(video),
                    "-t", f"{frames / fps:.3f}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
                    "-preset", "veryfast", "-c:a", "aac", "-movflags", "+faststart", str(original)], check=True)

    # 4. manifest for the frontend (contract in CLAUDE.md)
    manifest = {
        "clip": clip,
        "source": rel(video),
        "original": rel(original),
        "duration_sec": round(frames / fps, 2),
        "fps": round(fps, 2),
        "ai_view": rel(out_dir / f"{clip}_ai_view.mp4"),
        "compare": rel(compare) if compare.exists() else None,
        "surface": surface,
        "surfaces": surfaces,
        "scene": {k: v for k, v in (scene or {}).items() if k != "choices"} or None,
        "regions": [
            {"code": r, "label": LABELS.get(r, r),
             "video": rel(out_dir / f"{clip}_{r.lower()}.mp4") if ad else rel(video),  # no ad: original clip
             "ad_id": (ad or {}).get("id"), "brand": (ad or {}).get("brand"),
             "creative": rel(creative) if creative else None, "creative_method": methods.get(r),
             "reason": reason,
             "fit_score": (((scene or {}).get("choices") or {}).get(r) or {}).get("fit_score")}
            for r, (ad, reason, creative) in picks.items()
        ],
    }
    manifest_path = out_dir / f"{clip}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {rel(manifest_path)}")

    # 5. copy to frontend/demo/media/ (Git LFS): after commit + push the whole team sees it in the site
    if placed and not args.no_publish:
        run([PY, "pipeline/publish_media.py", clip])


if __name__ == "__main__":
    main()
