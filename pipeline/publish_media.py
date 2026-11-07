"""Publish a rendered clip to frontend/public/media/ (tracked with Git LFS) so the whole team gets it.

After `git add frontend/public/media`, commit and push, every teammate gets the videos with `git pull`
and the frontend lists the clip by itself (it reads media/index.json).

    python pipeline/publish_media.py melbourne                 # one clip: output/melbourne_*.mp4 + manifest
    python pipeline/publish_media.py --all                     # every clip rendered in output/
    python pipeline/publish_media.py melbourne --with-source   # also the original clip (before/after slider)

run.py and the backend's render jobs call this automatically at the end of every render.
The side-by-side compare video is not published (the frontend builds that view itself): it saves LFS quota.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"
PUBLIC = ROOT / "frontend" / "public"
MEDIA = PUBLIC / "media"
REGION_FILE = re.compile(r"^(?P<clip>.+)_(?P<code>[a-z]{2})\.mp4$")


def copy(src: Path, dst: Path) -> bool:
    """Copy only when the file changed, so re-publishing does not rewrite identical videos."""
    if dst.exists() and dst.stat().st_size == src.stat().st_size and dst.stat().st_mtime >= src.stat().st_mtime:
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


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
        """Copy a repo-relative file into media/<clip>/ and return its path as the site serves it."""
        nonlocal changed
        if not rel:
            return None
        src = ROOT / rel
        if not src.is_file():
            print(f"  warning: {rel} does not exist, skipped")
            return None
        dst = dest / name
        changed += copy(src, dst)
        return dst.relative_to(PUBLIC).as_posix()  # "media/<clip>/ro.mp4"

    source = m.get("source")
    regions = []
    for r in m.get("regions", []):
        code = r["code"].lower()
        if source and r.get("video") == source:  # region without an ad shows the original clip
            r["video"] = take(source, f"original{Path(source).suffix}")
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
    m.pop("compare", None)
    m.pop("original", None)
    uses_source = any(r["video"].startswith(f"media/{clip}/original") for r in regions)
    m["source"] = take(source, f"original{Path(source).suffix}") if source and (with_source or uses_source) else None
    m = {k: v for k, v in m.items() if v is not None}

    # nothing new: keep the old timestamp, so the site doesn't reload and git sees no change
    path = dest / "manifest.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if changed == 0 and {k: v for k, v in old.items() if k != "published"} == m:
        print(f"{clip}: already published, nothing changed")
        return dest
    m["published"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    dest.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    update_index(clip, [r["code"] for r in regions], m["published"])
    print(f"published {clip}: {len(regions)} versions, {changed} file(s) updated -> {dest.relative_to(ROOT).as_posix()}/")
    return dest


def update_index(clip: str, regions: list[str], published: str) -> None:
    """media/index.json: the list of clips the frontend shows in its video selector."""
    path = MEDIA / "index.json"
    index = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"clips": []}
    clips = [c for c in index.get("clips", []) if c.get("clip") != clip]
    clips.append({"clip": clip, "regions": regions, "published": published})
    index["clips"] = sorted(clips, key=lambda c: c["clip"])
    path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clip", nargs="?", help="clip name, e.g. melbourne")
    ap.add_argument("--all", action="store_true", help="publish every clip rendered in output/")
    ap.add_argument("--with-source", action="store_true", help="also publish the original clip (large)")
    args = ap.parse_args()
    if not args.clip and not args.all:
        ap.error("give a clip name or --all")
    for clip in rendered_clips() if args.all else [args.clip]:
        publish(clip, args.with_source)
    print("next: git add frontend/public/media && git commit && git push (videos go through Git LFS)")


if __name__ == "__main__":
    main()
