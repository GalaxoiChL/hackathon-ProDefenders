# CLAUDE.md: ghidul proiectului (pentru echipă și pentru Claude Code)

> Hackathon ITFest 2026, CSIE, sponsor **Adobe**. Tema: *„Marketing Reimagined: Build the Next Generation of AI-Powered Marketing Tools”*.
> Răspunde în **română**. Prioritatea e un **demo care merge**, nu perfecțiunea.

## Ideea

**Reclame în video adaptate țării în care se află privitorul, puse de AI.**
În același clip (film, vlog, stream), un panou de pe stradă arată *Pizza Bunicii, 19 lei* pentru cine îl vede din România, *Burger Bros, $4.99* pentru cine e în SUA și altceva în Japonia.

AI-ul face ce face azi un om, manual, ore întregi în After Effects:
1. **găsește** spațiile publicitare din video (panouri, afișe, ecrane, autobuze)
2. **înțelege scena** (loc, moment al zilei, vreme, atmosferă) și verifică **brand safety**
3. **alege** reclama potrivită pentru fiecare țară și scenă, cu justificare
4. **generează** vizualul reclamei (API de imagini); textul exact îl pune codul din baza de date
5. **o inserează** realist: urmărește panoul și păstrează oamenii care trec prin fața lui

Piața există deja (Mirriad, Amazon Prime Video), dar e enterprise și manuală. Noi o facem **automat și self-service**, inclusiv pentru creatori de conținut.

## Criterii de jurizare (ce optimizăm)

| Criteriu | % | Cum îl atingem |
|---|---|---|
| Problem solving | 25 | oamenii sar peste reclame; o plasare în video nu poate fi sărită; catalog vechi transformat în inventar publicitar nou |
| AI-driven innovation | 25 | AI în fiecare pas: detecție, înțelegerea scenei, alegere, generare, segmentare |
| Technical excellence | 25 | pipeline curat, contracte JSON clare între module, fallback-uri |
| Third-party integrations | 15 | API de imagini (ideal Adobe Firefly), geolocație IP, Ollama |
| Product experience & demo | 10 | player cu 3 țări sincronizate și butonul „Arată ce vede AI-ul” |
| Bonus cost vs. valoare | +10 | cost per plasare: cenți; o editare manuală: ore de editor |

## Arhitectura

```
clip video
   │
   ├─▶ [A] detect_surfaces   ─▶ <clip>.surfaces.json   (unde sunt panourile)
   ├─▶ [B] analyze_scene     ─▶ <clip>.scene.json      (context + brand safety)
   │
   ├─▶ [B] choose_ads        ─▶ alegere din data/ads.json, per țară, cu motiv
   ├─▶ [C] generate_ad       ─▶ assets/generated/<clip>/<regiune>.png
   │
   ├─▶ [motor] insert_ad.py  ─▶ output/<clip>_<regiune>.mp4 + output/<clip>_ai_view.mp4
   └─▶ [F] manifest          ─▶ output/<clip>.manifest.json  ──▶ [E] frontend demo
```

AI-ul de analiză rulează **local** (Ollama, YOLO): e rapid, privat și gratuit. Doar generarea imaginilor merge în cloud.

## Împărțirea muncii: alege-ți o parte

Scrie-ți numele în coloana **Owner**, lucrează pe branch-ul indicat și deschide un Pull Request spre `main` când ai ceva funcțional.

| # | Parte | Ce înseamnă „gata” | Branch | Owner | Status |
|---|---|---|---|---|---|
| **Motor** | Inserare video (urmărire, oameni în față, versiuni pe țări) | ✅ merge pe clipul din Melbourne | `video-pipeline` | Alex + Claude | ✅ gata (v1) |
| **A** | Detectare automată spații publicitare (AI) | dai un clip și primești `surfaces.json` cu 4 colțuri per panou, fără click manual | `ai-detect` | Alex + Claude | 🟡 în lucru |
| **B** | Analiza scenei, brand safety și alegerea reclamei (Ollama `gemma3:4b`) | `scene.json` + pentru fiecare țară reclama aleasă și motivul („plouă, seară: cafea caldă”) | `ai-scene` | _liber_ | ⬜ |
| **C** | Generare reclame: API de imagini + text din baza de date | un PNG la formatul panoului, cu vizual generat și text exact puse de cod | `ad-generator` | _liber_ | ⬜ |
| **D** | Baza de date de reclame | `data/ads.json` cu 2–3 branduri inventate per țară (RO, US, JP), poze de produs, culori | `ads-db` | _liber_ | ⬜ |
| **E** | Frontend demo | player web cu țări sincronizate, selector de țară sau geolocație, buton „ce vede AI-ul”, dashboard advertiser | `frontend` | _liber_ | ⬜ |
| **F** | Orchestrare / backend | un singur script sau endpoint: clip → A → B → C → motor → `manifest.json` | `backend` | _liber_ | ⬜ |
| **G** | Pitch, clipuri demo, cifre cost/valoare | prezentare de 3 minute, 2–3 clipuri bune (cameră fixă, oameni prin fața panoului), calcule | `pitch` | _liber_ | ⬜ |

Dependențe: **E** poate începe imediat cu videoclipurile existente din `output/`. **C** are nevoie de formatul din **D**. **F** leagă totul la final; până atunci fiecare parte rulează singură, pe fișiere.

## Contracte între module (respectați formatul ca piesele să se lege)

Toate coordonatele sunt în **pixeli din cadrul original**. Colțurile sunt mereu în ordinea **stânga-sus, dreapta-sus, dreapta-jos, stânga-jos**.

**`data/ads.json`** (D → B, C)
```json
[
  {
    "id": "ro-pizza-bunicii",
    "region": "RO",
    "brand": "Pizza Bunicii",
    "category": "food",
    "headline": "Felia caldă, la tine în cartier",
    "price": "19 lei",
    "colors": { "bg": "#C81E23", "fg": "#FFFFFF", "accent": "#FFC800" },
    "product_image": "data/products/ro-pizza-bunicii.png",
    "fits": ["evening", "rain", "cold", "urban"],
    "avoid": ["violence", "accident", "sad"]
  }
]
```

**`<clip>.surfaces.json`** (A → motor)
```json
{ "clip": "melbourne", "surfaces": [
  { "id": "s1", "type": "billboard", "frame": 0, "corners": [[1071,356],[1221,369],[1223,565],[1071,559]],
    "aspect": 0.77, "confidence": 0.91 }
] }
```

**`<clip>.scene.json`** (B → C, F)
```json
{ "clip": "melbourne", "location": "urban street", "time_of_day": "day", "weather": "overcast",
  "mood": "busy", "brand_safety": { "safe": true, "reasons": [] },
  "choices": { "RO": { "ad_id": "ro-pizza-bunicii", "reason": "..." } } }
```

**`output/<clip>.manifest.json`** (F → E)
```json
{ "clip": "melbourne", "ai_view": "output/melbourne_ai_view.mp4",
  "regions": [ { "code": "RO", "label": "România", "video": "output/melbourne_ro.mp4",
                 "ad_id": "ro-pizza-bunicii", "reason": "..." } ] }
```

## Cum rulezi motorul (merge deja)

```bash
python -m venv .venv          # sau: python -m uv venv .venv
.venv/Scripts/pip install -r requirements.txt     # Windows; pe Mac/Linux: .venv/bin/pip
python pipeline/make_test_ads.py
python pipeline/insert_ad.py assets/clips/melbourne.mp4 \
  --corners assets/clips/melbourne.corners.json \
  --ad ro=assets/ads/ro_portrait.png --ad us=assets/ads/us_portrait.png --ad jp=assets/ads/jp_portrait.png \
  --out output/melbourne --track --occlude --debug --max-frames 480
python pipeline/side_by_side.py output/melbourne --versions ro us jp --out output/compare.mp4
```

Clipul de test nu e în git (prea mare). Se descarcă de pe [Pexels](https://www.pexels.com/video/people-walking-down-a-city-street-with-a-red-jacket-27817664/) și se salvează ca `assets/clips/melbourne.mp4`.

| Script | Rol |
|---|---|
| `pipeline/insert_ad.py` | motorul: urmărire (optical flow + omografie), pierdere și regăsire (SIFT), oameni în față (YOLO-seg), export pe țări + „AI view” |
| `pipeline/pick_corners.py` | marcare manuală a colțurilor (fallback până e gata **A**) |
| `pipeline/make_test_ads.py` | reclame placeholder RO/US/JP |
| `pipeline/side_by_side.py` | video cu țările una lângă alta, sincronizate |
| `pipeline/contact_sheet.py` | imagine cu cadre-cheie pentru verificare rapidă |

## Reguli de lucru

- **Nu lucrăm direct pe `main`.** Branch-ul tău, apoi Pull Request.
- `git pull` des. Commit-uri mici, cu mesaje clare.
- **Nu urcăm** videoclipuri, `output/`, greutăți de modele (`*.pt`) sau `.env`; sunt în `.gitignore`.
- **Cheile API** stau doar în `.env` (ex. `IMAGE_API_KEY=...`), niciodată în cod, chat sau commit.
- Branduri **inventate** în demo (nu Pizza Hut sau McDonald's reale) și clipuri cu licență liberă (Pexels).

## Note pentru Claude Code

- Mediu de dezvoltare: Windows, Python 3.14 în `.venv`, GPU RTX 3060 6 GB (PyTorch e momentan pe CPU), Ollama local cu `gemma3:4b`.
- Optimizează pentru demo: fallback-uri sigure (ex. rezultate pre-randate) în loc de funcții fragile.
- Respectă contractele JSON de mai sus. Dacă trebuie schimbate, actualizează și acest fișier.
- Limite cunoscute ale motorului: urmărirea poate aluneca la mișcări foarte bruște; reclama e puțin prea „curată” față de scenă (de îmbunătățit armonizarea); ~0,7 s/cadru pe CPU.
