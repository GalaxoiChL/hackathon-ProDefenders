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
| GET | `/api/markets` | **cele 15 piețe demo** (US, RO, JP + 12 din Europa), cu brandul reclamei: opțiunile din selector |
| GET | `/api/countries/{code}` | o singură țară |
| GET | `/api/geo?country=` | țara privitorului + piața demo pe care e mapată (`market`, `market_match`) |
| GET | `/api/clips` | lista clipurilor randate |
| GET | `/api/clips/{clip}` | `manifest.json` + `video_url` / `ai_view_url` gata de pus în `<video>` |
| GET | `/api/clips/{clip}/play?country=` | **versiunea pentru privitorul ăsta** + reclama + toate regiunile |
| GET | `/api/clips/{clip}/scene` | analiza scenei + brand safety (task 2) |
| GET | `/api/clips/{clip}/surfaces` | spațiile publicitare (AI sau marcate manual) |
| GET | `/api/clips/{clip}/stats?views=` | dashboard: spații, vizibilitate, venit estimat, cost vs. valoare |
| GET | `/api/ads?region=`, `/api/ads/{id}` | baza de reclame |
| POST | `/api/jobs` | pornește pipeline-ul pentru un clip: `{clip, max_frames?, regions?}` rulează `pipeline/run.py` (detecție AI, analiza scenei, reclame reale, manifest), iar backend-ul adaugă `stats`. Cu `ads`/`corners` explicite rulează direct `insert_ad.py` |
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

## Piețele demo (15)

| | Piețe |
|---|---|
| implicit | **RO** |
| în afara Europei | **US**, **JP** |
| Europa | **GB, DE, FR, IT, ES, NL, BE, PL, SE, AT, PT, GR** |

Le schimbi cu `MARKETS=...` în `.env`. `DEFAULT_REGION` trebuie să fie una dintre ele, altfel serverul nu pornește și spune de ce.

- Selectorul din frontend ia opțiunile din `/api/markets`.
- Geolocația IP mapează **orice** țară pe cea mai apropiată piață, după aceleași reguli ca mai jos. De exemplu CH → DE, IE → GB, MD → RO, BR → PT, CN → JP, CZ → RO.
- Fiecare piață are o reclamă exemplu cu brand inventat, text în limba locală și preț în moneda locală (`backend/store.py`). Are și imagini placeholder în `assets/ads/<cc>.png` și `<cc>_portrait.png`, desenate cu `python backend/tools/make_market_ads.py`.
- Jobul randează implicit **câte o versiune pentru fiecare piață care are o imagine**, deci până la 15. Pentru altă țară, trimite explicit `"ads": {"BR": "cale/imagine.png"}`.

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

## Prospectare advertiseri: căutare de firme + emailuri + licitație

Două unelte AI care aduc advertiseri pentru spațiile din video:

**1. Căutarea de firme locale** (`POST /api/outreach/campaigns`)
1. găsește firmele din categoria cerută într-un oraș al pieței prin OpenStreetMap (gratuit, fără cheie). Dacă e setat `BRAVE_API_KEY`, caută și cu Brave Search.
2. exclude implicit lanțurile mari (McDonald's, KFC…), fiindcă vrem firme **regionale**
3. citește site-ul firmei (cel mult 3 pagini, respectând `robots.txt`) ca să afle emailul public de contact și ce face firma
4. **AI-ul** (Ollama `gemma3:4b`) dă un scor de potrivire între 0 și 100, cu motiv, și verifică brand safety (exclude jocuri de noroc, tutun etc.)
5. scrie **emailul personalizat în limba țării**, cu link de licitație semnat pentru fiecare firmă

**2. Emailurile automate**: niciun email nu pleacă fără un om care l-a aprobat:

```
ciornă ──(PATCH editează / approve / reject)──▶ aprobat ──(send, confirm=true)──▶ outbox sau trimis
```

| Regulă (impusă de cod, nu de AI) | De ce |
|---|---|
| `OUTREACH_SEND_ENABLED=false` (implicit): emailurile ajung doar ca fișiere `.eml` în `output/outbox/` | nimic nu pleacă din greșeală |
| `OUTREACH_TEST_RECIPIENT=adresa@ta`: **toate** emailurile merg la tine | demo sigur, cu emailuri reale în inbox |
| link de dezabonare + headerul `List-Unsubscribe` în fiecare email; cine se dezabonează nu mai primește nimic | GDPR / CAN-SPAM |
| subsol fix: cine suntem, de unde avem adresa, cum se oprește | transparență |
| adresele de tip `prenume.nume@` sunt sărite implicit | sunt date personale (GDPR) |
| limită zilnică (`OUTREACH_DAILY_LIMIT`, implicit 20) | fără spam |

⚠️ În unele țări (de ex. Germania) emailul comercial nesolicitat e interzis chiar și între firme. Pentru demo folosește `OUTREACH_TEST_RECIPIENT`.

**3. Licitația**: fiecare clip × piață e un spațiu publicitar (`/api/placements`). Prețul minim e CPM-ul pieței × numărul de privitori, de exemplu DE: $10,5 × 10.000 / 1000 = $105. Firma deschide linkul din email (`/bid/<token>`), vede clipul și trimite oferta. Linkul e semnat (HMAC), deci nu poate fi falsificat sau ghicit. Cea mai mare ofertă câștigă: `/api/placements/{id}/bids`.

| Metodă | Ruta | Ce face |
|---|---|---|
| POST | `/api/outreach/campaigns` | `{market, category, city?, clip?, limit, min_score}` pornește căutarea în fundal |
| GET | `/api/outreach/campaigns/{id}` | stare, jurnal, câte emailuri sunt în fiecare stare |
| GET | `/api/outreach/campaigns/{id}/leads` | firmele găsite, cu scor AI și motiv |
| GET | `/api/outreach/campaigns/{id}/emails` | ciornele |
| PATCH | `/api/outreach/emails/{id}` | editează subiectul sau textul |
| POST | `/api/outreach/emails/{id}/approve` · `/reject` | aprobă sau respinge |
| POST | `/api/outreach/campaigns/{id}/send` | `{confirm: true, approve_all?}` trimite emailurile aprobate |
| GET | `/api/outreach/status` | dacă trimiterea e pornită, SMTP, limită, AI |
| GET | `/api/placements`, `/api/placements/{id}/bids` | spațiile și ofertele |
| POST | `/api/bids` | `{token, amount_usd, company?, message?}` |
| GET | `/bid/{token}` | pagina de licitație din email |

Exemplu:
```bash
curl -X POST localhost:8000/api/outreach/campaigns -H "Content-Type: application/json"      -d '{"market": "RO", "category": "food", "limit": 5}'
```
Categorii: `food`, `drinks`, `retail`, `beauty`, `fitness`, `hotel`, `any`. Fără Ollama, scorul și emailul (RO / EN) se fac după reguli fixe, iar răspunsul spune `"ai": "rules"`. Serverul public Overpass e des supraîncărcat, așa că se încearcă automat alte servere, iar rezultatele rămân în cache o săptămână (`output/outreach_cache/`).

## Fallback-uri (demo-ul nu rămâne gol)

| Lipsește | Ce face serverul |
|---|---|
| `output/<clip>.manifest.json` | îl construiește din fișierele `output/<clip>_<xx>.mp4` existente |
| `<clip>.surfaces.json` | folosește colțurile marcate manual în `assets/clips/<clip>.corners.json` |
| `data/ads.json` (sau o piață lipsă din el) | reclamele reale din `data/ads.json` au prioritate; piețele pe care nu le acoperă primesc exemplul din backend. Dacă fișierul lipsește complet, se folosesc 15 reclame exemplu, câte una pe piață (Pizza Bunicii, Burger Bros, Sakura Ramen, Brezelhaus, Café Lumière…) |
| PNG-urile generate (task 2) | jobul folosește `assets/ads/<xx>_portrait.png` (există pentru toate cele 15 piețe) |
| internet (geolocație) | regiunea implicită |

## Configurare (`.env`, opțional)

Vezi `.env.example` în rădăcina repo-ului.
