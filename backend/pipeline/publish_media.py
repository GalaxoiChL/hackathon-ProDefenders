"""Publish a rendered clip to frontend/demo/media/ (videos tracked with Git LFS) so the whole team gets it.

The demo site (frontend/demo/index.html) opens by double-click, with nothing installed, and plays every
clip listed in frontend/demo/media/catalog.js. After `git add frontend/demo/media`, commit and push,
teammates get the new clip with `git pull`.

    python backend/pipeline/publish_media.py melbourne                 # one clip: output/melbourne_*.mp4 + manifest
    python backend/pipeline/publish_media.py --all                     # every clip rendered in backend/output/
    python backend/pipeline/publish_media.py melbourne --with-source   # also the full source clip (large)

run.py and the backend's render jobs call this automatically at the end of every render.
The side-by-side compare video is not published (the site builds that view itself): it saves LFS quota.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # backend/
OUTPUT = ROOT / "output"
DEMO = ROOT.parent / "frontend" / "demo"               # the double-click site lives with the frontend
MEDIA = DEMO / "media"
REGION_FILE = re.compile(r"^(?P<clip>.+)_(?P<code>[a-z]{2})\.mp4$")


def copy(src: Path, dst: Path) -> bool:
    """Copy only when the file changed, so re-publishing does not rewrite identical videos."""
    if dst.exists() and dst.stat().st_size == src.stat().st_size and dst.stat().st_mtime >= src.stat().st_mtime:
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def load_manifest(clip: str) -> dict:
    """output/<clip>.manifest.json, or one built from the rendered files (insert_ad.py run by hand)."""
    path = OUTPUT / f"{clip}.manifest.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    regions = [
        {"code": m["code"].upper(), "label": m["code"].upper(), "video": f"output/{p.name}"}
        for p in sorted(OUTPUT.glob(f"{clip}_*.mp4"))
        if (m := REGION_FILE.match(p.name)) and m["clip"] == clip
    ]
    if not regions:
        raise SystemExit(f"nothing rendered for {clip!r} in output/")
    ai = OUTPUT / f"{clip}_ai_view.mp4"
    return {"clip": clip, "ai_view": f"output/{ai.name}" if ai.exists() else None, "regions": regions}


def rendered_clips() -> list[str]:
    names = {p.name.removesuffix(".manifest.json") for p in OUTPUT.glob("*.manifest.json")}
    names |= {m["clip"] for p in OUTPUT.glob("*.mp4") if (m := REGION_FILE.match(p.name))}
    return sorted(names)


def publish(clip: str, with_source: bool = False) -> Path:
    m = load_manifest(clip)
    dest = MEDIA / clip
    changed = 0

    def take(rel: str | None, name: str) -> str | None:
        """Copy a repo-relative file into media/<clip>/ and return its path relative to demo/."""
        nonlocal changed
        if not rel:
            return None
        src = ROOT / rel
        if not src.is_file():
            print(f"  warning: {rel} does not exist, skipped")
            return None
        dst = dest / name
        changed += copy(src, dst)
        return dst.relative_to(DEMO).as_posix()  # "media/<clip>/ro.mp4"

    source = m.get("source")
    regions = []
    for r in m.get("regions", []):
        code = r["code"].lower()
        if source and r.get("video") == source:  # region without an ad shows the original clip
            r["video"] = take(source, f"source{Path(source).suffix}")
        else:
            r["video"] = take(r.get("video"), f"{code}.mp4")
        if r.get("creative"):
            r["creative"] = take(r["creative"], f"{code}_creative{Path(r['creative']).suffix}")
        if r["video"]:
            regions.append(r)
    if not regions:
        raise SystemExit(f"no rendered video found for {clip!r}")

    m["regions"] = regions
    m["ai_view"] = take(m.get("ai_view"), "ai_view.mp4")
    # the clip without ads, for the before/after slider: a trimmed copy if the pipeline made one, else the source
    m["original"] = take(m.get("original"), "original.mp4")
    uses_source = any(r["video"].startswith(f"media/{clip}/source") for r in regions)
    if source and (with_source or uses_source):
        published_source = take(source, f"source{Path(source).suffix}")
        m["original"] = m["original"] or published_source
    m.pop("compare", None)
    m.pop("source", None)
    m = {k: v for k, v in m.items() if v is not None}

    # nothing new: keep the old timestamp, so the site doesn't reload and git sees no change
    path = dest / "manifest.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if changed == 0 and {k: v for k, v in old.items() if k != "published"} == m:
        print(f"{clip}: already published, nothing changed")
        return dest
    m["published"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    dest.mkdir(parents=True, exist_ok=True)
    write_json(path, m)
    write_catalog()
    print(f"published {clip}: {len(regions)} versions, {changed} file(s) updated -> {dest.relative_to(ROOT.parent).as_posix()}/")
    return dest


def write_catalog() -> None:
    """Every published clip, in two forms the site reads.

    index.json: for the dev server (the site re-checks it every 30 s, so a pulled clip shows up live).
    catalog.js: for demo/index.html opened by double-click; a page opened from disk may not fetch JSON,
    but it can load a classic <script>, so the manifests are embedded in it.
    """
    manifests = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(MEDIA.glob("*/manifest.json"))]
    write_json(MEDIA / "index.json", {"clips": [
        {"clip": m["clip"], "regions": [r["code"] for r in m["regions"]], "published": m.get("published")}
        for m in manifests]})
    body = json.dumps({"clips": manifests}, indent=2, ensure_ascii=False)
    (MEDIA / "catalog.js").write_text(
        "// Generated by pipeline/publish_media.py: the clips demo/index.html can play. Do not edit by hand.\n"
        f"window.__PRODEFENDERS_MEDIA__ = {body};\n", encoding="utf-8", newline="\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clip", nargs="?", help="clip name, e.g. melbourne")
    ap.add_argument("--all", action="store_true", help="publish every clip rendered in output/")
    ap.add_argument("--with-source", action="store_true", help="also publish the full source clip (large)")
    args = ap.parse_args()
    if not args.clip and not args.all:
        ap.error("give a clip name or --all")
    for clip in rendered_clips() if args.all else [args.clip]:
        publish(clip, args.with_source)
    print("next: git add frontend/demo/media && git commit && git push (videos go through Git LFS)")


if __name__ == "__main__":
    main()
