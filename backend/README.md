# Backend: server API (FastAPI)

Stă între pipeline (task 1 și 2) și demo (task 3). Citește fișierele produse de pipeline, servește video-urile, alege țara privitorului după IP, calculează cifrele pentru dashboard și pornește pipeline-ul în fundal.

## Pornire

```bash
python -m venv .venv
.venv/Scripts/pip install -r backend/requirements.txt      # doar serverul (fără torch)
.venv/Scripts/python -m uvicorn backend.app:app --reload --port 8000
```

- Documentația interactivă e la http://localhost:8000/docs
- Dacă există `frontend/index.html`, frontendul e servit la http://localhost:8000/, de pe aceeași origine, deci fără probleme de CORS la demo.
- Pentru `POST /api/jobs` trebuie instalate și dependențele motorului: `pip install -r requirements.txt`.

Teste: `.venv/Scripts/python -m pytest -q tests`

## Endpoint-uri

| Metodă | Ruta | Ce face |
|---|---|---|
| GET | `/api/health` | starea serverului, clipurile găsite, sursa reclamelor |
| GET | `/api/regions` | RO / US / JP: nume, steag, monedă, CPM |
| GET | `/api/geo?country=` | țara privitorului și regiunea demo potrivită |
| GET | `/api/clips` | lista clipurilor randate |
| GET | `/api/clips/{clip}` | `manifest.json` + `video_url` / `ai_view_url` gata de pus în `<video>` |
| GET | `/api/clips/{clip}/play?country=` | **versiunea pentru privitorul ăsta** + reclama + toate regiunile |
| GET | `/api/clips/{clip}/scene` | analiza scenei + brand safety (task 2) |
| GET | `/api/clips/{clip}/surfaces` | spațiile publicitare (AI sau marcate manual) |
| GET | `/api/clips/{clip}/stats?views=` | dashboard: spații, vizibilitate, venit estimat, cost vs. valoare |
| GET | `/api/ads?region=`, `/api/ads/{id}` | baza de reclame |
| POST | `/api/jobs` | pornește pipeline-ul pentru un clip; la final scrie `output/<clip>.manifest.json` |
| GET | `/api/jobs`, `/api/jobs/{id}` | progres (cadre procesate / total, %) și ultimele linii de log |
| GET | `/output/…`, `/assets/…`, `/data/…` | fișiere statice; video-urile acceptă cereri Range (seek în player) |

Exemplu de job:
```bash
curl -X POST localhost:8000/api/jobs -H "Content-Type: application/json" \
     -d '{"clip": "melbourne", "max_frames": 480}'
```

## Cum se alege țara

Câștigă primul care răspunde:
1. `?country=JP`, util când schimbi țara de mână în demo
2. headerul `X-Demo-Country: JP`, pentru selectorul din frontend
3. headerul `CF-IPCountry`, dacă serverul stă în spatele Cloudflare
4. geolocație IP prin ip-api.com (gratuit, fără cheie, cu cache)
5. `DEFAULT_REGION`, pentru localhost, rețea locală sau când lookup-ul eșuează

Pentru țările care nu au versiune proprie se folosește cea mai apropiată piață demo (MD→RO, CA→US, KR→JP etc.), iar dacă nu există una, regiunea implicită.

## Fallback-uri (demo-ul nu rămâne gol)

| Lipsește | Ce face serverul |
|---|---|
| `output/<clip>.manifest.json` | îl construiește din fișierele `output/<clip>_<xx>.mp4` existente |
| `<clip>.surfaces.json` | folosește colțurile marcate manual în `assets/clips/<clip>.corners.json` |
| `data/ads.json` | folosește 3 reclame exemplu (Pizza Bunicii, Burger Bros, Sakura Ramen) |
| PNG-urile generate (task 2) | jobul folosește `assets/ads/<xx>_portrait.png` |
| internet (geolocație) | regiunea implicită |

## Configurare (`.env`, opțional)

Vezi `.env.example` în rădăcina repo-ului.
