# CLAUDE.md: ghidul proiectului (pentru echipă și pentru Claude Code)

> Hackathon ITFest 2026, CSIE, sponsor **Adobe**. Tema: *„Marketing Reimagined: Build the Next Generation of AI-Powered Marketing Tools”*.
> Răspunde în **română**. Prioritatea e un **demo care merge**, nu perfecțiunea.

## Ideea

**Reclame în video adaptate țării în care se află privitorul, puse de AI.**
În același clip (film, vlog, stream), un panou de pe stradă arată o reclamă Pizza Hut pentru cine îl vede din România, alt brand pentru cine e în SUA și altul în Japonia.

AI-ul face ce face azi un om, manual, ore întregi în After Effects:
1. **găsește** spațiile publicitare din video (panouri, afișe, ecrane, autobuze)
2. **înțelege scena** (loc, moment al zilei, vreme, atmosferă) și verifică **brand safety**
3. **alege** reclama potrivită pentru fiecare țară și scenă, cu justificare
4. **adaptează** reclama reală a brandului la fiecare suprafață (vertical pe panou, lat pe autobuz), fără să o deformeze: AI-ul recompune doar fundalul din jur
5. **o inserează** realist: urmărește panoul și păstrează oamenii care trec prin fața lui

Piața există deja (Mirriad, Amazon Prime Video), dar e enterprise și manuală. Noi o facem **automat și self-service**, inclusiv pentru creatori de conținut.

## Criterii de jurizare (ce optimizăm)

| Criteriu | % | Cum îl atingem |
|---|---|---|
| Problem solving | 25 | oamenii sar peste reclame; o plasare în video nu poate fi sărită; catalog vechi transformat în inventar publicitar nou |
| AI-driven innovation | 25 | AI în fiecare pas: detecție, înțelegerea scenei, alegere, generare, segmentare |
| Technical excellence | 25 | pipeline curat, contracte JSON clare între module, fallback-uri |
| Third-party integrations | 15 | API de imagini (ideal Adobe Firefly), geolocație IP, Ollama, OpenStreetMap (căutare de firme), SMTP |
| Product experience & demo | 10 | player cu 3 țări sincronizate și butonul „Arată ce vede AI-ul” |
| Bonus cost vs. valoare | +10 | cost per plasare: cenți; o editare manuală: ore de editor |

## Arhitectura

```
clip video
   │
   ├─▶ [1] detect_surfaces   ─▶ <clip>.surfaces.json   (unde sunt panourile)
   ├─▶ [2] analyze_scene     ─▶ <clip>.scene.json      (context + brand safety)
   │
   ├─▶ [2] choose_ads        ─▶ alegere din data/ads.json [4], per țară, cu motiv
   ├─▶ [2] generate_ad       ─▶ assets/generated/<clip>/<regiune>.png
   │
   ├─▶ [1] insert_ad.py      ─▶ output/<clip>_<regiune>.mp4 + output/<clip>_ai_view.mp4
   └─▶ [1] manifest          ─▶ output/<clip>.manifest.json
                                         │
                              [B] backend/ (FastAPI) ─▶ /api/... + video-uri ──▶ [3] frontend demo
                                  geolocație IP, dashboard, joburi pipeline
```

AI-ul de analiză rulează **local** (Ollama, YOLO): e rapid, privat și gratuit. Doar generarea imaginilor merge în cloud.

## Structura repo-ului

```
backend/                 tot ce ține de server și de motorul AI
  start.py               ← pornește backend-ul (o singură comandă)
  app.py, config.py, …   serverul API (FastAPI, pachetul Python `backend`), outreach/, tools/
  pipeline/              motorul video AI (run.py, insert_ad.py, detect_surfaces.py, …)
  data/ assets/ output/  datele: reclame, clipuri sursă, randări
  tests/                 testele serverului
  requirements.txt       dependențele serverului (ușoare, fără torch)
  requirements-pipeline.txt   dependențele motorului AI (torch, YOLO, OpenCV)
  .env.example           copiază-l în backend/.env
  .venv/                 creat de start.py (nu e în git)
frontend/                site-ul (React + Vite)
  npm start              ← pornește frontend-ul (o singură comandă)
  src/                   codul site-ului
  demo/                  site-ul de dublu-click (index.html) + clipurile echipei în demo/media/ (Git LFS)
```

Căile din contracte și manifeste (`data/...`, `output/...`, `assets/...`) sunt **relative la `backend/`** și se servesc la aceleași URL-uri (`/output/...`).

## Împărțirea muncii: 4 task-uri, unul pentru fiecare

Scrie-ți numele în coloana **Owner**, lucrează pe branch-ul indicat și deschide un Pull Request spre `main` când ai ceva funcțional.

| # | Task | Ce include | Ce înseamnă „gata” | Branch | Owner |
|---|---|---|---|---|---|
| **1** | **Pipeline video AI** | motorul de inserare (✅ v1 gata), detectarea automată a panourilor cu AI, scriptul care leagă toți pașii și scrie `manifest.json` | dai un clip și primești automat videoclipurile pe țări + „AI view” + `manifest.json`, fără click manual | `video-pipeline` | Alex + Claude |
| **2** | **AI de scenă și adaptarea reclamelor** | ✅ analiza scenei, brand safety și alegerea reclamei cu motiv (`analyze_scene.py`, gata). **Rămâne:** adaptarea reclamei la formatul suprafeței cu AI (recompunerea fundalului prin API de imagini), în locul decupării din `adapt_ad.py` | câte un PNG per țară în `assets/generated/<clip>/<regiune>.png`, exact la formatul (`aspect`) suprafeței, fără text tăiat | `ai-ads` | analiză: Alex + Claude; adaptare: _liber_ |
| **3** | **Frontend demo** | player web cu țările sincronizate, selector de țară sau geolocație IP, buton „Arată ce vede AI-ul”, dashboard pentru advertiser (spații, vizibilitate, venit estimat) | demo-ul complet rulează în browser, citind `manifest.json` | `frontend` | _liber_ |
| **4** | **Date, conținut și pitch** | `data/ads.json` cu 2–3 branduri reale per țară (RO, US, JP) și reclamele lor reale (imagini salvate în `data/creatives/`), 2–3 clipuri demo (cameră fixă, oameni prin fața panoului), cifre cost/valoare, prezentarea de 3 minute | baza de date completă, clipurile alese, slide-urile și pitch-ul repetat | `content` | _liber_ |
| **B** | **Server API** | FastAPI în `backend/`: servește manifestele și video-urile (cu seek), 15 piețe demo (US, RO, JP + 12 din Europa), geolocație IP care mapează orice țară din lume pe cea mai apropiată piață, cifrele pentru dashboard, joburi care rulează pipeline-ul și scriu `manifest.json`, fallback-uri pentru demo; **prospectare advertiseri**: AI-ul caută firme locale (OpenStreetMap), le califică și le scrie emailuri în limba lor, cu aprobare umană, iar firmele licitează pe spațiile din video | ✅ v1 gata: `python backend/start.py`, testele trec; detalii în `backend/README.md` | `backend` | _liber_ |

Dependențe: **3** poate începe imediat cu videoclipurile existente din `backend/output/`. **2** are nevoie de formatul `ads.json` (de mai jos) pentru textul reclamelor; până e gata baza de date, folosește exemplul din contract. **1** leagă totul la final; până atunci fiecare task rulează singur, pe fișiere.

## Reclamele: reclame reale ale brandurilor + AI care adaptează formatul (decizie de echipă)

- Folosim **reclame reale** ale unor branduri cunoscute din fiecare țară (ex. Pizza Hut). Nu le facem noi.
- **Produsul și reclama rămân cele reale.** AI-ul nu inventează produse și nu schimbă mesajul brandului.
- Problema pe care o rezolvă AI-ul: reclama reală vine într-un singur format, dar trebuie să încapă pe suprafețe foarte diferite (în clipul de test: panou vertical 0,74, firmă 1,55, autobuz 2,92). AI-ul extinde sau recompune **fundalul** din jurul reclamei ca să se potrivească formatului, fără să o deformeze.
- În prezentare: mențiunea *„Branduri folosite strict demonstrativ, fără afiliere”*. Videoclipurile cu branduri reale nu se publică online.
- API de imagini: Firefly nu e disponibil. Încercăm întâi **Gemini** (cheie în `backend/.env` ca `GEMINI_API_KEY`), apoi Replicate/FLUX. Furnizorul trebuie să fie interschimbabil.
- **Fallback sigur pentru demo:** dacă API-ul nu merge, se folosește reclama reală, încadrată fără deformare (crop/padding pe culoarea dominantă). Demo-ul nu are voie să depindă de internet.

## Contracte între module (respectați formatul ca piesele să se lege)

Toate coordonatele sunt în **pixeli din cadrul original**. Colțurile sunt mereu în ordinea **stânga-sus, dreapta-sus, dreapta-jos, stânga-jos**.

**`data/ads.json`** (task 4 → task 2)
```json
[
  {
    "id": "ro-pizza-hut",
    "region": "RO",
    "brand": "Pizza Hut",
    "category": "food",
    "creative": "data/creatives/ro-pizza-hut.jpg",
    "creative_source": "https://... (de unde e luată reclama)",
    "colors": { "bg": "#C8102E", "fg": "#FFFFFF" },
    "fits": ["evening", "rain", "cold", "urban"],
    "avoid": ["violence", "accident", "sad"]
  }
]
```

**`<clip>.surfaces.json`** (task 1, intern: detecție → motor)
```json
{ "clip": "melbourne", "surfaces": [
  { "id": "s1", "type": "billboard", "frame": 0, "corners": [[1071,356],[1221,369],[1223,565],[1071,559]],
    "aspect": 0.77, "confidence": 0.91 }
] }
```

**`<clip>.scene.json`** (task 2 → task 1)
```json
{ "clip": "melbourne", "location": "urban street", "time_of_day": "day", "weather": "overcast",
  "mood": "busy", "brand_safety": { "safe": true, "reasons": [] },
  "choices": { "RO": { "ad_id": "ro-pizza-hut", "reason": "..." } } }
```

Codurile de regiune (`region`, `code`, cheile din `choices`) sunt coduri de țară **ISO 3166-1 alpha-2**. Orice țară din lume poate avea o versiune.

**`output/<clip>.manifest.json`** (task 1 → task 3)
```json
{ "clip": "melbourne", "ai_view": "output/melbourne_ai_view.mp4",
  "regions": [ { "code": "RO", "label": "România", "video": "output/melbourne_ro.mp4",
                 "ad_id": "ro-pizza-hut", "reason": "..." } ] }
```
Opțional, `"stats": { "frames": 480, "lost_frames": 12, "fps": 25, "width": 1920, "height": 1080 }`. Îl scrie jobul din backend, iar dashboard-ul îl folosește pentru vizibilitate.

**API backend** (backend → task 3): frontendul citește prin server, nu direct fișierele. Lista completă e în `backend/README.md` și la `/docs`.
- `GET /api/markets` întoarce cele 15 piețe demo, adică opțiunile din selector. `GET /api/countries` întoarce toate țările lumii.
- `GET /api/clips/{clip}/play?country=XX` (orice cod ISO) întoarce `{ viewer: {country, name, flag, market, region, match, source}, current: {code, video_url, ad_id, reason}, ad, ai_view_url, regions: [...] }`. `match` arată de ce s-a ales versiunea: `exact`, `language`, `subregion`, `continent` sau `default`.
- `GET /api/clips/{clip}/stats?views=N` întoarce `{ spaces, visibility, brand_safety, regions: [{code, impressions, revenue_usd}], totals, cost_vs_value, assumptions }`
- `POST /api/jobs {clip}` pornește pipeline-ul, iar `GET /api/jobs/{id}` arată progresul. La final se scrie `output/<clip>.manifest.json`.
- **Marketplace (filme):** `GET /api/movies` întoarce tabelul de filme (un rând pe clip). `GET /api/movies/{clip}` întoarce locurile de reclamă din film (`places`, câte unul pe suprafața din `surfaces.json`), fiecare cu oferta pe fiecare țară (`offers`). `POST /api/placements/{id}/bids {company, email, amount_usd, category?, message?}` primește oferta oricărei firme. Un spațiu de vânzare are id-ul `clip:suprafață:ȚARĂ`, de exemplu `melbourne:s2:DE`. Emailurile ofertanților nu sunt publice.
- Fișierele sunt servite la `/output/...`, `/assets/...` și `/data/...` (căile din manifest + `/` în față).

## Cum rulezi (o comandă pentru fiecare parte)

Din rădăcina repo-ului, în două terminale:

```bash
python backend/start.py          # backend: http://localhost:8000 (API docs la /docs)
npm --prefix frontend start      # frontend: http://localhost:5173 (sau: cd frontend && npm start)
```

- `backend/start.py` creează la prima rulare `backend/.venv` și instalează `backend/requirements.txt`; apoi reinstalează doar când se schimbă un fișier de requirements. Opțiuni: `--reload` (repornește la modificări de cod), `--port 8000`, `--pipeline` (instalează și motorul AI: torch, YOLO, OpenCV; descărcare mare).
- `npm start` instalează pachetele (`npm install`, rapid când sunt deja la zi) și pornește Vite. Frontend-ul trimite `/api` la backend-ul de pe portul 8000; dacă backend-ul nu rulează, citește direct fișierele din `backend/output/` și `frontend/demo/media/`.
- Testele backend-ului: `backend/.venv/Scripts/python -m pytest -q backend/tests`

**Motorul AI** (randare pe țări, rulat de mână sau prin `POST /api/jobs`), după `python backend/start.py --pipeline`:

```bash
# reclamele reale nu sunt în git: descarcă fiecare `creative` din backend/data/ads.json de la `creative_source`
backend/.venv/Scripts/python.exe backend/pipeline/run.py backend/assets/clips/melbourne.mp4 --max-frames 480
```

Progresul randării: `Get-Content backend\output\progress.txt` (se actualizează la fiecare 30 de cadre).

`run.py` face tot lanțul: detectare AI (dacă nu există deja `output/<clip>.surfaces.json`), analiza AI a scenei cu Ollama (dacă nu există `output/<clip>.scene.json`; Ollama trebuie pornit), alegerea reclamei pe țară, adaptarea la formatul suprafeței, randarea tuturor țărilor + „AI view” + video comparativ, apoi scrie `output/<clip>.manifest.json`.

Folosește automat ce produc celelalte task-uri, dacă există, altfel are fallback sigur:
- `data/ads.json` (task 4): **obligatoriu**, doar reclame reale; implicit se randează fiecare regiune care are o reclamă acolo
- `output/<clip>.scene.json` (generat automat de `analyze_scene.py`) pentru alegerea AI și motiv; dacă Ollama nu merge: primul brand al regiunii
- `assets/generated/<clip>/<regiune>.png` (task 2) pentru reclama adaptată de AI; fără el: `adapt_ad.py` încadrează reclama fără deformare

**Demo-ul se deschide fără nimic instalat:** dublu-click pe `frontend/demo/index.html` (Chrome sau Edge). Site-ul e într-un singur fișier și redă clipurile din `frontend/demo/media/`; are și butonul **Upload**, care pune o reclamă pe un video ales de tine direct în browser. Videoclipurile ajung în demo prin Git LFS: la final, `run.py` (și joburile din backend) rulează `backend/pipeline/publish_media.py`, care copiază versiunile pe țări, „AI view”, clipul original scurtat și manifestul în `frontend/demo/media/<clip>/` și regenerează `frontend/demo/media/catalog.js`. Faci commit + push la `frontend/demo/media`, iar colegii primesc clipul cu `git pull`. O singură dată pe fiecare laptop: `git lfs install`. Manual: `python backend/pipeline/publish_media.py <clip>` sau `--all`. Codul site-ului din `frontend/demo/index.html` se reface cu `cd frontend && npm run build:demo` (doar când se schimbă frontend-ul, nu la clipuri noi). Limita gratuită GitHub LFS: 1 GB stocare și 1 GB descărcări pe lună, deci publicăm doar clipurile finale.

Clipul de test nu e în git (prea mare). Se descarcă de pe [Pexels](https://www.pexels.com/video/people-walking-down-a-city-street-with-a-red-jacket-27817664/) și se salvează ca `backend/assets/clips/melbourne.mp4`.

Scripturile de mai jos sunt în `backend/pipeline/`. Exemplele din comentariile lor (`python pipeline/run.py assets/clips/...`) se rulează **din folderul `backend/`**, unde le rulează și backend-ul. Modelele YOLO și SAM 2 se descarcă în `backend/models/`, iar Stable Diffusion și OWLv2 în cache-ul Hugging Face (`~/.cache/huggingface`). Pentru GPU, după `start.py --pipeline` instalează PyTorch cu CUDA (comanda e în `backend/requirements-pipeline.txt`).

| Script | Rol |
|---|---|
| `pipeline/run.py` | **comanda principală:** tot lanțul, de la clip la `manifest.json` |
| `pipeline/publish_media.py` | publică randarea în `frontend/demo/media/` (Git LFS), ca demo-ul s-o arate la toată echipa |
| `pipeline/analyze_scene.py` | **AI local (Ollama `gemma3:4b`):** descrie scena, verifică brand safety (scenă nesigură = fără reclamă), alege reclama potrivită per țară cu scor și motiv în română; scrie `scene.json` |
| `pipeline/adapt_ad.py` | încadrează o reclamă la formatul suprafeței fără deformare (fallback pentru AI-ul din task 2) |
| `pipeline/insert_ad.py` | motorul: urmărire (optical flow + omografie), pierdere și regăsire (SIFT), oameni în față (YOLO-seg), export pe țări + „AI view” |
| `pipeline/detect_surfaces.py` | **AI:** găsește singur suprafețele publicitare (OWLv2 + SAM 2) și scrie `surfaces.json`; `insert_ad.py --corners` îl acceptă direct |
| `pipeline/pick_corners.py` | marcare manuală a colțurilor (fallback dacă detectorul greșește) |
| `pipeline/side_by_side.py` | video cu țările una lângă alta, sincronizate |
| `pipeline/contact_sheet.py` | imagine cu cadre-cheie pentru verificare rapidă |

## Reguli de lucru

- **Nu lucrăm direct pe `main`.** Branch-ul tău, apoi Pull Request.
- `git pull` des. Commit-uri mici, cu mesaje clare.
- **Nu urcăm** `backend/output/`, clipurile sursă, greutăți de modele (`*.pt`) sau `backend/.env`; sunt în `.gitignore`. **Excepție:** videoclipurile finale de demo, doar prin `publish_media.py` în `frontend/demo/media/` (Git LFS, vezi mai sus). Repo-ul e privat, deci rămân vizibile doar echipei.
- Emailurile către firme pleacă **doar** aprobate de un om și cu `OUTREACH_SEND_ENABLED=true`; în demo, cu `OUTREACH_TEST_RECIPIENT`.
- **Cheile API** stau doar în `backend/.env` (ex. `IMAGE_API_KEY=...`), niciodată în cod, chat sau commit.
- Reclame **reale** de branduri, folosite doar demonstrativ (cu mențiunea de neafiliere în prezentare); clipurile video doar cu licență liberă (Pexels).

## Note pentru Claude Code

- Mediu de dezvoltare: Windows, Python 3.14 în `backend/.venv`, GPU RTX 3060 6 GB (PyTorch e momentan pe CPU), Ollama local cu `gemma3:4b`.
- Optimizează pentru demo: fallback-uri sigure (ex. rezultate pre-randate) în loc de funcții fragile.
- Respectă contractele JSON de mai sus. Dacă trebuie schimbate, actualizează și acest fișier.
- Urmărirea are 3 moduri: `local` (panoul vizibil), `coast` (panoul ascuns de autobuz sau ieșit din cadru: poziția urmează mișcarea camerei, autobuzul e segmentat și trece prin fața reclamei), `lost` (se caută prin SIFT până reapare).
- Limite cunoscute: reclama e puțin prea „curată” față de scenă (de îmbunătățit armonizarea); ~0,7–1,5 s/cadru pe CPU (PyTorch pe GPU ar accelera).
