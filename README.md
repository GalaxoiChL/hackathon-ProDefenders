# Swapboard

> Echipa ProDefenders · repo `hackathon-ProDefenders`

Reclame în video adaptate țării privitorului, puse de AI: același clip arată pe un panou de pe stradă altă reclamă pentru fiecare țară. Hackathon ITFest 2026 (sponsor Adobe).

## Pornire

Din rădăcina repo-ului, în două terminale:

```bash
python backend/start.py          # backend: http://localhost:8000 (API docs la /docs)
npm --prefix frontend start      # frontend: http://localhost:5173
```

Prima rulare instalează singură dependențele (`backend/.venv`, `frontend/node_modules`). Fără nimic instalat, demo-ul se deschide și cu dublu-click pe `frontend/demo/index.html`.

## Structura

| Folder | Ce conține |
|---|---|
| `backend/` | serverul API (FastAPI), motorul video AI (`pipeline/`), datele (`data/`, `assets/`, `output/`), testele, configurarea (`.env`) |
| `frontend/` | site-ul (React + Vite) și demo-ul de dublu-click (`demo/`) |

Detalii: [CLAUDE.md](CLAUDE.md) (ghidul proiectului) și [backend/README.md](backend/README.md) (API).

## Reguli de lucru

1. Fiecare lucrează pe branch-ul lui (`frontend`, `backend` etc.), nu direct pe `main`.
2. Fă `git pull` des ca să ai ultimele modificări.
3. Commit-uri mici, cu mesaje clare.
4. Când o parte e gata: Pull Request și merge în `main`.
