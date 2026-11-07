"""Runs the video pipeline in the background and writes output/<clip>.manifest.json.

One job at a time (the engine already uses the whole CPU). Jobs are queued in memory;
progress is parsed from the engine's stdout ("  30/480 frames ...").

Inputs are resolved with the same fallbacks as the rest of the backend:
  corners: <clip>.surfaces.json (AI detection, task 1) -> assets/clips/<clip>.corners.json (manual)
  ads:     scene.json choices + assets/generated/<clip>/<region>.png (task 2) -> assets/ads/<region>_portrait.png
"""
from __future__ import annotations

import json
import queue
import re
import subprocess
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from . import regions
from .config import Settings
from .models import ClipStats, JobRequest, Manifest, ManifestRegion
from .stats import probe_video
from .store import BadRequest, NotFound, Store, check_clip

PROGRESS_RE = re.compile(r"^\s*(\d+)/(\d+|\?) frames")
SUMMARY_RE = re.compile(r"frames: (\d+), billboard lost in (\d+)")


@dataclass
class Job:
    id: str
    clip: str
    command: list[str]
    status: str = "queued"           # queued | running | done | failed
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    frames_done: int = 0
    frames_total: int | None = None
    returncode: int | None = None
    error: str | None = None
    manifest: str | None = None
    log: deque = field(default_factory=lambda: deque(maxlen=200))
    # resolved inputs, needed to write the manifest afterwards
    regions: list[str] = field(default_factory=list)
    out_prefix: Path | None = None
    video: Path | None = None
    debug: bool = True
    mode: str = "insert"             # "run": pipeline/run.py (task 1) | "insert": insert_ad.py directly

    def public(self, log_lines: int = 20) -> dict:
        pct = None
        if self.frames_total:
            pct = round(100 * min(self.frames_done, self.frames_total) / self.frames_total, 1)
        if self.status == "done":
            pct = 100.0
        return {
            "id": self.id, "clip": self.clip, "status": self.status,
            "created": self.created, "started": self.started, "finished": self.finished,
            "progress": {"frames_done": self.frames_done, "frames_total": self.frames_total, "percent": pct},
            "returncode": self.returncode, "error": self.error, "manifest": self.manifest,
            "regions": self.regions, "mode": self.mode, "log": list(self.log)[-log_lines:],
        }


class JobRunner:
    def __init__(self, settings: Settings, store: Store):
        self.s = settings
        self.store = store
        self.jobs: dict[str, Job] = {}
        self._queue: queue.Queue[Job] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._lock = threading.Lock()

    # ---------- input resolution ----------
    def _corners_file(self, req: JobRequest, clip: str) -> Path:
        if req.corners:
            p = self.s.root / req.corners
            if not p.is_file():
                raise NotFound(f"corners file not found: {req.corners}")
            return p
        surf = self.store.surfaces_or_none(clip)
        if surf is None or not surf.surfaces:
            raise NotFound(f"no surfaces.json or corners.json for {clip!r}; mark them with pipeline/pick_corners.py")
        manual = self.s.clips_dir / f"{clip}.corners.json"
        if getattr(surf, "source", None) == "manual" and manual.is_file():
            return manual
        # the engine reads {"corners": [...]}: write the best-scoring detected surface in that format
        best = max(surf.surfaces, key=lambda x: x.confidence or 0)
        tmp = self.s.output_dir / f"{clip}.job_corners.json"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps({"frame": best.frame, "corners": best.corners, "surface": best.id}),
                       encoding="utf-8")
        return tmp

    def _ads(self, req: JobRequest, clip: str) -> dict[str, Path]:
        if req.ads:
            ads = {}
            for code, rel in req.ads.items():
                if not regions.is_country(code):
                    raise BadRequest(f"unknown country code: {code!r} (use ISO 3166-1 alpha-2, e.g. FR)")
                p = self.s.root / rel
                if not p.is_file():
                    raise NotFound(f"ad image not found for {code}: {rel}")
                ads[code.upper()] = p
            return ads
        # Every market with an ad image gets a version. Generated (task 2) beats placeholder.
        # Lower priority first, so better sources overwrite.
        ads: dict[str, Path] = {}
        sources = [(self.s.assets_dir / "ads", ("{cc}.png", "{cc}_portrait.png")),
                   (self.s.assets_dir / "generated" / clip, ("{cc}.png",))]
        for folder, patterns in sources:
            if not folder.is_dir():
                continue
            for p in sorted(folder.glob("*.png")):
                for pat in patterns:
                    prefix, suffix = pat.split("{cc}")
                    stem = p.name[len(prefix):len(p.name) - len(suffix)] if p.name.endswith(suffix) else ""
                    if len(stem) == 2 and regions.is_country(stem):
                        ads[stem.upper()] = p
        # by default render only the demo markets (a stray PNG must not add a 16th version)
        ads = {cc: p for cc, p in ads.items() if cc in self.s.markets}
        if not ads:
            raise NotFound("no ad images for the demo markets "
                           "(assets/generated/<clip>/<cc>.png or assets/ads/<cc>.png)")
        return {cc: ads[cc] for cc in self.s.markets if cc in ads}  # market order: US, RO, JP, ...

    def build(self, req: JobRequest) -> Job:
        clip = check_clip(req.clip)
        video = self.s.root / (req.video or f"assets/clips/{clip}.mp4")
        if not video.is_file():
            raise NotFound(f"video not found: {self.store.rel(video) if video.is_relative_to(self.s.root) else video}")
        run_py = self.s.root / "pipeline" / "run.py"
        if run_py.is_file() and not req.corners and not req.ads:
            # task 1's orchestrator: AI surface detection, scene analysis, real creatives, manifest
            cmd = [self.s.python, "-u", str(run_py), str(video)]
            if req.regions:
                bad = [r for r in req.regions if not regions.is_country(r)]
                if bad:
                    raise BadRequest(f"unknown country codes: {bad}")
                cmd += ["--regions", *[r.upper() for r in req.regions]]
            if req.max_frames:
                cmd += ["--max-frames", str(req.max_frames)]
            return Job(id=uuid.uuid4().hex[:12], clip=clip, command=cmd, mode="run",
                       regions=[r.upper() for r in req.regions or []], out_prefix=self.s.output_dir / clip,
                       video=video, debug=True, frames_total=req.max_frames or None)
        corners = self._corners_file(req, clip)
        ads = self._ads(req, clip)
        out_prefix = self.s.output_dir / clip
        cmd = [self.s.python, "-u", str(self.s.root / "pipeline" / "insert_ad.py"), str(video),
               "--corners", str(corners), "--out", str(out_prefix)]
        for code, path in ads.items():
            cmd += ["--ad", f"{code.lower()}={path}"]
        if req.track:
            cmd.append("--track")
        if req.occlude:
            cmd.append("--occlude")
        if req.debug:
            cmd.append("--debug")
        if req.max_frames:
            cmd += ["--max-frames", str(req.max_frames)]
        return Job(id=uuid.uuid4().hex[:12], clip=clip, command=cmd, regions=list(ads),
                   out_prefix=out_prefix, video=video, debug=req.debug,
                   frames_total=req.max_frames or None)

    # ---------- queue ----------
    def submit(self, req: JobRequest) -> Job:
        job = self.build(req)
        with self._lock:
            busy = next((j for j in self.jobs.values()
                         if j.clip == job.clip and j.status in ("queued", "running")), None)
            if busy:
                return busy  # same clip already in progress: don't render it twice
            self.jobs[job.id] = job
            self._queue.put(job)
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._work, daemon=True, name="pipeline-jobs")
                self._worker.start()
        return job

    def _work(self) -> None:
        while True:  # daemon thread: lives as long as the server
            self.run(self._queue.get())

    def run(self, job: Job) -> None:
        job.status, job.started = "running", time.time()
        summary = None
        try:
            if job.frames_total is None and job.video:
                probed = probe_video(job.video)
                job.frames_total = probed.frames if probed else None
            proc = subprocess.Popen(job.command, cwd=self.s.root, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.rstrip()
                if not line:
                    continue
                job.log.append(line)
                if m := PROGRESS_RE.match(line):
                    job.frames_done = int(m[1])
                    if m[2] != "?" and not job.frames_total:
                        job.frames_total = int(m[2])
                elif m := SUMMARY_RE.search(line):
                    summary = (int(m[1]), int(m[2]))
            job.returncode = proc.wait()
            if job.returncode != 0:
                raise RuntimeError(f"pipeline exited with code {job.returncode}")
            job.manifest = (self.adopt_manifest(job, summary) if job.mode == "run"
                            else self.write_manifest(job, summary))
            self.publish(job)
            job.status = "done"
        except Exception as e:  # report, don't crash the server
            job.status, job.error = "failed", str(e)
        finally:
            job.finished = time.time()

    def publish(self, job: Job) -> None:
        """Copy the result to demo/media/ (Git LFS) so the team gets it with git pull.

        Runs after the manifest is final (with `stats`); a failure is logged, the render still counts as done.
        """
        script = self.s.root / "pipeline" / "publish_media.py"
        if not script.is_file():
            return
        res = subprocess.run([self.s.python, str(script), job.clip], cwd=self.s.root, capture_output=True,
                             text=True, encoding="utf-8", errors="replace")
        job.log.extend(line for line in (res.stdout + res.stderr).splitlines() if line.strip())
        if res.returncode != 0:
            job.log.append(f"publish to demo/media/ failed (exit {res.returncode})")

    # ---------- manifest ----------
    def adopt_manifest(self, job: Job, summary: tuple[int, int] | None) -> str:
        """run.py wrote the manifest; validate it and add the optional `stats` block for the dashboard."""
        path = self.s.output_dir / f"{job.clip}.manifest.json"
        if not path.is_file():
            raise RuntimeError("pipeline finished but wrote no manifest.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        m = Manifest.model_validate(data)            # raises if the contract is broken
        job.regions = [r.code for r in m.regions]
        if summary:
            first = next((r.video for r in m.regions if r.video.startswith("output/")), None)
            probed = (probe_video(self.s.root / first) if first else None) or ClipStats()
            data["stats"] = ClipStats(frames=summary[0], lost_frames=summary[1], fps=probed.fps,
                                      width=probed.width, height=probed.height).model_dump(exclude_none=True)
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return self.store.rel(path)

    def write_manifest(self, job: Job, summary: tuple[int, int] | None) -> str:
        """Write output/<clip>.manifest.json in the CLAUDE.md contract (+ optional `stats`)."""
        clip, prefix = job.clip, job.out_prefix
        scene = self.store.scene_or_none(clip)
        regs = []
        for code in job.regions:
            video = prefix.parent / f"{prefix.name}_{code.lower()}.mp4"
            if not video.is_file():
                raise RuntimeError(f"expected output missing: {video.name}")
            choice = scene.choices.get(code) if scene else None
            regs.append(ManifestRegion(code=code, label=regions.label(code), video=self.store.rel(video),
                                       ad_id=choice.ad_id if choice else None,
                                       reason=choice.reason if choice else None))
        ai = prefix.parent / f"{prefix.name}_ai_view.mp4"
        probed = probe_video(prefix.parent / f"{prefix.name}_{job.regions[0].lower()}.mp4") or ClipStats()
        stats = ClipStats(frames=summary[0] if summary else probed.frames,
                          lost_frames=summary[1] if summary else None,
                          fps=probed.fps, width=probed.width, height=probed.height)
        manifest = Manifest(clip=clip, ai_view=self.store.rel(ai) if ai.is_file() else None,
                            regions=regs, stats=stats)
        path = self.s.output_dir / f"{clip}.manifest.json"
        path.write_text(manifest.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return self.store.rel(path)
