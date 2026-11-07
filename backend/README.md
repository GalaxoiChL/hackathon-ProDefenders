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
| GET | `/api/countries?q=&continent=` | **toate cele 250 de țări** (ISO 3166-1): nume RO/EN, steag, monedă, limbă, continent, CPM, pentru selector |
| GET | `/api/countries/{code}` | o singură țară |
| GET | `/api/geo?country=` | țara privitorului, cu toate detaliile |
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
1. `?country=FR`, orice cod ISO din lume, util când schimbi țara de mână în demo
2. headerul `X-Demo-Country: JP`, pentru selectorul din frontend
3. headerul `CF-IPCountry`, dacă serverul stă în spatele Cloudflare
4. geolocație IP prin ip-api.com (gratuit, fără cheie, cu cache)
5. `DEFAULT_REGION`, pentru localhost, rețea locală sau când lookup-ul eșuează

Un cod necunoscut (de ex. `ZZ`) dat prin `?country=` întoarce eroarea 400. Dacă vine prin header, e ignorat.

## Orice țară, orice versiune

O „regiune” e pur și simplu țara pentru care s-a randat clipul (`output/<clip>_<cc>.mp4`). Orice țară poate avea versiunea ei: pui imaginea reclamei în `assets/generated/<clip>/fr.png` (sau `assets/ads/fr.png`), iar jobul randează automat și versiunea FR.

Privitorii din țări fără versiune proprie primesc **cea mai apropiată versiune**, în ordinea:

| Potrivire (`viewer.match`) | Exemplu, cu versiunile RO / US / JP |
|---|---|
| `exact` | US → US |
| `language`: aceeași limbă | MD → RO (română), CA / AU → US (engleză) |
| `subregion`: aceeași zonă (UN M49) | PL → RO (Europa de Est), KR → JP (Asia de Est) |
| `continent` | FR → RO, BR → US, IN → JP |
| `default` | EG → RO (nimic randat în Africa) |

Datele țărilor sunt în `backend/countries.json` (nume în română din CLDR, limbă oficială, monedă, regiune UN M49, CPM estimat după nivelul de venit). Le regenerezi cu `pip install babel` și `python backend/tools/build_countries.py`.

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
