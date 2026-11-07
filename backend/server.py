"""Backend API for the demo: serves processed clips, detects the viewer's country, runs the pipeline.

    .venv\\Scripts\\python.exe backend\\server.py            # http://localhost:8000  (docs: /docs)

Endpoints
  GET  /api/health
  GET  /api/clips                  processed clips (from output/*.manifest.json)
  GET  /api/clips/{clip}           full manifest + ready-to-use URLs for videos and creatives
  GET  /api/geo[?country=JP]       viewer's country from their IP (ip-api.com), override for demos
  GET  /api/ads                    the real ads catalogue (data/ads.json)
  POST /api/process                upload a clip (multipart "file"), runs pipeline/run.py in background
  GET  /api/jobs/{job_id}          status + progress of a processing job
  /output/...  /clips/...          rendered videos / source clips (HTTP range requests supported)
  /                                the frontend, if web/ exists (task 3)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"
CLIPS = ROOT / "assets" / "clips"
JOBS_DIR = OUTPUT / "jobs"
DEFAULT_COUNTRY = "RO"

app = FastAPI(title="AI ad placement in video", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

OUTPUT.mkdir(exist_ok=True)
CLIPS.mkdir(parents=True, exist_ok=True)
JOBS_DIR.mkdir(exist_ok=True)
app.mount("/output", StaticFiles(directory=OUTPUT), name="output")
app.mount("/clips", StaticFiles(directory=CLIPS), name="clips")


def url_for(path: str | None) -> str | None:
    """Repo-relative path from a manifest -> URL served by this backend."""
    if not path:
        return None
    if path.startswith("output/"):
        return "/" + path
    if path.startswith("assets/clips/"):
        return "/clips/" + path[len("assets/clips/"):]
    return None


def load_manifest(clip: str) -> dict:
    path = OUTPUT / f"{clip}.manifest.json"
    if not path.exists():
        raise HTTPException(404, f"clip {clip!r} not processed")
    m = json.loads(path.read_text(encoding="utf-8"))
    m["urls"] = {"source": url_for(m.get("source")), "ai_view": url_for(m.get("ai_view")),
                 "compare": url_for(m.get("compare"))}
    for r in m.get("regions", []):
        r["video_url"] = url_for(r.get("video"))
        r["creative_url"] = url_for(r.get("creative"))
    return m


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/clips")
def clips():
    out = []
    for p in sorted(OUTPUT.glob("*.manifest.json")):
        m = load_manifest(p.name[: -len(".manifest.json")])
        out.append({"clip": m["clip"], "regions": [r["code"] for r in m.get("regions", [])],
                    "compare_url": m["urls"]["compare"], "summary": (m.get("scene") or {}).get("summary_ro")})
    return out


@app.get("/api/clips/{clip}")
def clip(clip: str):
    return load_manifest(clip)


@app.get("/api/ads")
def ads():
    path = ROOT / "data" / "ads.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


# ---------- geolocation (third-party integration) ----------
_geo_cache: dict[str, dict] = {}


def lookup_ip(ip: str | None) -> dict:
    """ip-api.com (free, no key). Local/private IPs -> look up this machine's public IP instead,
    which is what you want when the demo runs on the laptop itself."""
    local = not ip or ip.startswith(("127.", "10.", "192.168.", "::1", "172.16.", "localhost"))
    key = "self" if local else ip
    if key in _geo_cache:
        return _geo_cache[key]
    url = "http://ip-api.com/json/" + ("" if local else ip) + "?fields=status,countryCode,country,city"
    try:
        with urllib.request.urlopen(url, timeout=4) as r:
            data = json.loads(r.read())
        if data.get("status") == "success":
            res = {"country": data["countryCode"], "country_name": data.get("country"),
                   "city": data.get("city"), "source": "ip-api.com"}
            _geo_cache[key] = res
            return res
    except Exception:  # offline at the venue: never break the demo
        pass
    return {"country": DEFAULT_COUNTRY, "country_name": None, "city": None, "source": "fallback"}


@app.get("/api/geo")
def geo(request: Request, country: str | None = None):
    if country:  # demo override: /api/geo?country=JP
        return {"country": country.upper(), "source": "override"}
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return lookup_ip(forwarded or (request.client.host if request.client else None))


# ---------- processing jobs ----------
_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def _run_job(job_id: str, clip_path: Path, max_frames: int) -> None:
    job = _jobs[job_id]
    log = JOBS_DIR / f"{job_id}.log"
    cmd = [sys.executable, "pipeline/run.py", str(clip_path)]
    if max_frames:
        cmd += ["--max-frames", str(max_frames)]
    job.update(status="running", started=time.time())
    with open(log, "w", encoding="utf-8") as f:
        proc = subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT,
                              env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    job.update(status="done" if proc.returncode == 0 else "failed", finished=time.time(), returncode=proc.returncode)


@app.post("/api/process")
async def process(file: UploadFile = File(...), max_frames: int = Form(0)):
    with _lock:
        if any(j["status"] in ("queued", "running") for j in _jobs.values()):
            raise HTTPException(409, "a clip is already being processed; try again when it finishes")
        name = re.sub(r"[^a-zA-Z0-9_-]+", "_", Path(file.filename or "clip").stem).strip("_")[:40] or "clip"
        dest = CLIPS / f"{name}.mp4"
        dest.write_bytes(await file.read())
        job_id = uuid.uuid4().hex[:8]
        _jobs[job_id] = {"id": job_id, "clip": name, "status": "queued", "created": time.time()}
    threading.Thread(target=_run_job, args=(job_id, dest, max_frames), daemon=True).start()
    return _jobs[job_id]


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    j = _jobs.get(job_id)
    if not j:
        raise HTTPException(404, "unknown job")
    log = JOBS_DIR / f"{job_id}.log"
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines() if log.exists() else []
    steps = [l for l in lines if l.startswith("$ ")]
    stage = ("detect" if any("detect_surfaces" in s for s in steps) else "starting")
    if any("analyze_scene" in s for s in steps):
        stage = "scene"
    if any("insert_ad" in s for s in steps):
        stage = "render"
    if any("side_by_side" in s for s in steps):
        stage = "compare"
    progress = next((l.strip() for l in reversed(lines) if "/" in l and "frames" in l), None)
    m = re.search(r"(\d+)/(\d+) frames", progress or "")
    return {**j, "stage": stage, "progress": progress,
            "percent": round(100 * int(m.group(1)) / int(m.group(2))) if m else None,
            "log_tail": lines[-8:], "manifest_url": f"/api/clips/{j['clip']}" if j["status"] == "done" else None}


# frontend (task 3) is served from web/ if it exists
if (ROOT / "web").is_dir():
    app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
