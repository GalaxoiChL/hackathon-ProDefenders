"""AI scene understanding + brand safety + ad choice per country, with a local vision model (Ollama).

1. samples a few frames from the clip and asks gemma3 (vision) to describe the scene for an
   advertiser: location, time of day, weather, mood, audience, and whether it is brand-safe
2. for every region, asks the model which of that region's real ads (data/ads.json) fits the
   scene best, with a short reason in Romanian that the demo shows to the jury
3. writes output/<clip>.scene.json (contract in CLAUDE.md), which run.py picks up

Runs fully local: video frames never leave the laptop.

    python pipeline/analyze_scene.py assets/clips/melbourne.mp4
"""
from __future__ import annotations

import argparse
import base64
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
OLLAMA = "http://localhost:11434/api/generate"
MODEL = "gemma3:4b"

SCENE_SCHEMA = {
    "type": "object",
    "properties": {
        "location": {"type": "string", "description": "e.g. busy downtown street, mall, beach"},
        "city_guess": {"type": "string"},
        "time_of_day": {"type": "string", "enum": ["morning", "midday", "afternoon", "evening", "night"]},
        "weather": {"type": "string", "enum": ["sunny", "overcast", "rain", "snow", "fog", "indoor"]},
        "mood": {"type": "string", "description": "one or two words"},
        "audience": {"type": "string", "description": "who is in the scene, in a few words"},
        "tags": {"type": "array", "items": {"type": "string"},
                 "description": "short lowercase tags like urban, lunch, students, cold, traffic"},
        "brand_safe": {"type": "boolean"},
        "brand_safety_issues": {"type": "array", "items": {"type": "string"},
                                "description": "violence, accident, emergency, protest, sad, explicit... empty if none"},
        "summary_ro": {"type": "string", "description": "one sentence in Romanian describing the scene for an advertiser"},
    },
    "required": ["location", "time_of_day", "weather", "mood", "audience", "tags",
                 "brand_safe", "brand_safety_issues", "summary_ro"],
}

CHOICE_SCHEMA = {
    "type": "object",
    "properties": {
        "ad_id": {"type": "string"},
        "fit_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "reason_ro": {"type": "string", "description": "one or two short sentences in Romanian"},
    },
    "required": ["ad_id", "fit_score", "reason_ro"],
}


def ask(prompt: str, schema: dict, images: list[bytes] | None = None, timeout: int = 300) -> dict:
    body = {"model": MODEL, "prompt": prompt, "stream": False, "format": schema,
            "options": {"temperature": 0.2}}
    if images:
        body["images"] = [base64.b64encode(b).decode() for b in images]
    req = urllib.request.Request(OLLAMA, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(json.loads(r.read())["response"])


def ollama_up() -> bool:
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3).read()
        return True
    except (urllib.error.URLError, OSError):
        return False


def sample_frames(video: Path, n: int, max_side: int = 768) -> list[bytes]:
    """n frames spread over the clip, downscaled and JPEG-encoded (enough for scene understanding)."""
    cap = cv2.VideoCapture(str(video))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    out = []
    for i in range(n):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int((i + 0.5) * total / n))
        ok, f = cap.read()
        if not ok:
            continue
        s = max_side / max(f.shape[:2])
        f = cv2.resize(f, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else f
        out.append(cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes())
    cap.release()
    return out


def describe_scene(frames: list[bytes]) -> dict:
    prompt = (
        "These are frames from one video clip. You are a media buyer deciding which outdoor ad to place "
        "on a billboard visible in this clip. Describe the scene for an advertiser. Judge brand safety "
        "strictly: unsafe if there is violence, an accident, an emergency, a protest, grief, or explicit content. "
        "Answer only with JSON matching the schema. The field summary_ro MUST be written in Romanian "
        "(limba română), all other fields in English."
    )
    return ask(prompt, SCENE_SCHEMA, frames)


def choose(region: str, scene: dict, candidates: list[dict]) -> dict:
    """Pick the best ad for this region and scene. Rules first (brand safety), then the model."""
    if not scene.get("brand_safe", True):
        return {"ad_id": None, "fit_score": 0,
                "reason": "Scenă nesigură pentru branduri (" + ", ".join(scene.get("brand_safety_issues", [])) + "): nu plasăm reclamă."}
    issues = set(map(str.lower, scene.get("brand_safety_issues", [])))
    allowed = [a for a in candidates if not issues & set(map(str.lower, a.get("avoid", [])))]
    if not allowed:
        return {"ad_id": None, "fit_score": 0, "reason": "Toate reclamele regiunii exclud acest tip de scenă."}
    ads_text = "\n".join(
        f"- id={a['id']} | brand={a['brand']} | category={a.get('category')} | message={a.get('description', '')} "
        f"| fits={','.join(a.get('fits', []))}" for a in allowed)
    prompt = (
        f"Scene (from a video, viewers are in region {region}): {json.dumps(scene, ensure_ascii=False)}\n\n"
        f"Real ads available for viewers in {region}:\n{ads_text}\n\n"
        "Pick the ad that fits this scene and moment best for these viewers. Give a fit score 0-100 and a short, "
        "concrete reason in Romanian that mentions what in the scene matches the ad (time of day, weather, place, "
        "audience). Write it naturally for a marketer, without English words or JSON field names in parentheses. "
        "Use only an id from the list. Answer only with JSON."
    )
    res = ask(prompt, CHOICE_SCHEMA)
    ids = {a["id"] for a in allowed}
    if res.get("ad_id") not in ids:  # model invented an id: fall back to the first allowed ad
        res["ad_id"] = allowed[0]["id"]
    return {"ad_id": res["ad_id"], "fit_score": int(res.get("fit_score", 0)), "reason": res.get("reason_ro", "")}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("--frames", type=int, default=3, help="frames sampled for the scene description")
    ap.add_argument("--ads", type=Path, default=ROOT / "data" / "ads.json")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    clip = args.video.stem
    out = args.out or ROOT / "output" / f"{clip}.scene.json"

    if not ollama_up():
        raise SystemExit("Ollama is not running on localhost:11434 (start the Ollama app)")
    ads = json.loads(args.ads.read_text(encoding="utf-8"))

    t0 = time.time()
    scene = describe_scene(sample_frames(args.video, args.frames))
    print(f"scene ({time.time() - t0:.1f}s): {scene.get('summary_ro')}")
    print(f"  brand safe: {scene.get('brand_safe')}  issues: {scene.get('brand_safety_issues')}")

    choices = {}
    for region in dict.fromkeys(a["region"] for a in ads):
        t1 = time.time()
        c = choose(region, scene, [a for a in ads if a["region"] == region])
        choices[region] = c
        print(f"  {region}: {c['ad_id']} (fit {c['fit_score']}, {time.time() - t1:.1f}s) - {c['reason']}")

    result = {"clip": clip, "model": MODEL, **scene,
              "brand_safety": {"safe": scene.get("brand_safe", True), "reasons": scene.get("brand_safety_issues", [])},
              "choices": choices}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
