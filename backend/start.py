"""Start the backend with one command, from any folder:

    python backend/start.py               # API server at http://localhost:8000 (docs at /docs)
    python backend/start.py --pipeline    # also install the AI video pipeline (torch, YOLO: large download)
    python backend/start.py --reload      # restart on code changes (development)

First run creates backend/.venv and installs backend/requirements.txt into it. Later runs reinstall
only when a requirements file changed, so a normal start takes a second. Settings come from
backend/.env (copy backend/.env.example); every value has a demo-safe default.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import venv
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
REPO = BACKEND.parent
VENV = BACKEND / ".venv"
PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
STAMP = VENV / ".installed-requirements"


def requirement_files(pipeline: bool) -> list[Path]:
    files = [BACKEND / "requirements.txt"]
    if pipeline or (STAMP.is_file() and "pipeline" in STAMP.read_text(encoding="utf-8")):
        files.append(BACKEND / "requirements-pipeline.txt")  # once installed, keep it up to date
    return files


def fingerprint(files: list[Path]) -> str:
    h = hashlib.sha256()
    for f in files:
        h.update(f.name.encode() + b"\0" + f.read_bytes())
    return ("pipeline " if len(files) > 1 else "") + h.hexdigest()


def ensure_env(pipeline: bool) -> None:
    if not PY.is_file():
        print(f"creating {VENV.relative_to(REPO)} ...", flush=True)
        venv.EnvBuilder(with_pip=True).create(VENV)
    files = requirement_files(pipeline)
    want = fingerprint(files)
    if STAMP.is_file() and STAMP.read_text(encoding="utf-8") == want:
        return
    print("installing " + ", ".join(f.relative_to(REPO).as_posix() for f in files) + " ...", flush=True)
    pip = [str(PY), "-m", "pip", "--disable-pip-version-check"]
    cmd = pip + ["install", "-q"]
    for f in files:
        cmd += ["-r", str(f)]
    subprocess.run(cmd, check=True)
    drop_conflicting_opencv(pip)
    STAMP.write_text(want, encoding="utf-8")


def drop_conflicting_opencv(pip: list[str]) -> None:
    """opencv-python and opencv-python-headless both install the `cv2` module: with both in one venv,
    removing or upgrading either breaks cv2. We use opencv-python (older venvs have the headless one)."""
    if subprocess.run(pip + ["show", "-q", "opencv-python-headless"], capture_output=True).returncode != 0:
        return
    print("replacing opencv-python-headless with opencv-python ...", flush=True)
    subprocess.run(pip + ["uninstall", "-y", "-q", "opencv-python-headless"], check=True)
    # the uninstall deleted the shared cv2 files: put opencv-python's back
    subprocess.run(pip + ["install", "-q", "--force-reinstall", "--no-deps", "opencv-python"], check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to reach it from other devices")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--reload", action="store_true", help="restart on code changes")
    ap.add_argument("--pipeline", action="store_true", help="also install the AI video pipeline dependencies")
    ap.add_argument("--no-install", action="store_true", help="skip the dependency check")
    args = ap.parse_args()

    if not args.no_install:
        try:
            ensure_env(args.pipeline)
        except subprocess.CalledProcessError as e:
            raise SystemExit(f"dependency install failed (exit {e.returncode}); see the pip output above")

    cmd = [str(PY), "-m", "uvicorn", "backend.app:app", "--host", args.host, "--port", str(args.port)]
    if args.reload:
        cmd += ["--reload", "--reload-dir", str(BACKEND)]
    print(f"backend: http://localhost:{args.port}  (API docs: http://localhost:{args.port}/docs)", flush=True)
    try:
        # the repo root as working dir, so the `backend` package is importable
        sys.exit(subprocess.call(cmd, cwd=REPO))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
