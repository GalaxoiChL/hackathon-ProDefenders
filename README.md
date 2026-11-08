# SwapBoard

**One video, a different billboard ad in every country, placed by AI.**

A street billboard in a film, vlog or stream shows a local brand to viewers in Romania, another to viewers in Japan, and another in the US. Today an editor does this by hand in After Effects, for hours per shot. SwapBoard does it automatically: it finds the ad spaces in the video, understands the scene, picks a fitting ad for each country, fits the real ad to the surface and places it in the video so that people walking past stay in front of it.

Built in 10 hours at **ITFest 2026** (theme: *Marketing Reimagined: AI-Powered Marketing Tools*).

## How it works

```
video clip
  1. Find the billboard   OWLv2 + SAM 2          → where the ad spaces are (4 corners each)
  2. Read the scene       Gemma 3 (Ollama)       → place, time, weather, mood, brand safety
  3. Pick the ad          Gemma 3                → best ad per country, with a reason
  4. Fit the ad           Stable Diffusion       → extends the background so the real ad fits the shape, no crop or stretch
  5. Place in video       OpenCV + YOLO11 + FFmpeg → tracks the surface, keeps people in front, renders one video per country
  6. Serve by country     ip-api                 → each viewer gets the version for their market
```

All the AI models run **locally** (fast, private, free). The external services are only IP geolocation, OpenStreetMap and email.

## What's in the app

| Tab | What it does |
|---|---|
| **Watch** | plays the video in the version for your country; switch country or show "what the AI sees" |
| **Compare** | the same scene for several countries, side by side and in sync |
| **Marketplace** | movies and their ad spaces, with open bids per country |
| **Companies** | the advertisers and what they bid on |
| **Outreach** | AI finds local businesses near a placement (OpenStreetMap), writes them an email in their language, and sends it only after a person approves it |
| **How it works** | the models and services behind each step |

## Run it

**No install:** double-click `frontend/demo/index.html`. It plays the pre-rendered demo from disk.

**Full app**, from the repo root, in two terminals (needs Python 3 and Node.js 20.19+):

```bash
python backend/start.py          # API on http://localhost:8000 (docs at /docs)
npm --prefix frontend start      # site on http://localhost:5173
```

The first run installs the dependencies by itself (`backend/.venv`, `frontend/node_modules`). To also install the AI video engine (PyTorch, YOLO, OpenCV) and render new clips, run `python backend/start.py --pipeline`. Optional settings (SMTP, Ollama, etc.) go in `backend/.env`; see `backend/.env.example`.

The demo videos are stored with [Git LFS](https://git-lfs.com): run `git lfs install` before cloning.

## Project structure

| Folder | Contents |
|---|---|
| `backend/` | FastAPI server, the AI video pipeline (`pipeline/`), advertiser outreach (`outreach/`), data, tests |
| `frontend/` | the website (React + Vite + Tailwind) and the no-install demo (`demo/`) |

API reference: [backend/README.md](backend/README.md).

## Tech

Python · FastAPI · PyTorch · OpenCV · Ultralytics (YOLO11, SAM 2) · Hugging Face (OWLv2, Diffusers) · Ollama (Gemma 3) · FFmpeg · React · TypeScript · Vite · Tailwind CSS

## Team

ProDefenders: <!-- add names / GitHub profiles here if you want them public -->

---

*Brands appearing in the demo are used for demonstration only, with no affiliation.*
