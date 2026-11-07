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
| Third-party integrations | 15 | API de imagini (ideal Adobe Firefly), geolocație IP, Ollama |
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
   └─▶ [1] manifest          ─▶ output/<clip>.manifest.json  ──▶ [3] frontend demo
```

AI-ul de analiză rulează **local** (Ollama, YOLO): e rapid, privat și gratuit. Doar generarea imaginilor merge în cloud.

## Împărțirea muncii: 4 task-uri, unul pentru fiecare

Scrie-ți numele în coloana **Owner**, lucrează pe branch-ul indicat și deschide un Pull Request spre `main` când ai ceva funcțional.

| # | Task | Ce include | Ce înseamnă „gata” | Branch | Owner |
|---|---|---|---|---|---|
| **1** | **Pipeline video AI** | motorul de inserare (✅ v1 gata), detectarea automată a panourilor cu AI, scriptul care leagă toți pașii și scrie `manifest.json` | dai un clip și primești automat videoclipurile pe țări + „AI view” + `manifest.json`, fără click manual | `video-pipeline` | Alex + Claude |
| **2** | **AI de scenă și adaptarea reclamelor** | analiza scenei și brand safety cu Ollama `gemma3:4b`, alegerea reclamei per țară cu motiv, adaptarea reclamei la formatul fiecărei suprafețe (vezi „Reclamele” mai jos) | `scene.json` cu alegerile și motivele, plus câte un PNG per țară exact la formatul (`aspect`) suprafeței | `ai-ads` | _liber_ |
| **3** | **Frontend demo** | player web cu țările sincronizate, selector de țară sau geolocație IP, buton „Arată ce vede AI-ul”, dashboard pentru advertiser (spații, vizibilitate, venit estimat) | demo-ul complet rulează în browser, citind `manifest.json` | `frontend` | _liber_ |
| **4** | **Date, conținut și pitch** | `data/ads.json` cu 2–3 branduri reale per țară (RO, US, JP) și reclamele lor reale (imagini salvate în `data/creatives/`), 2–3 clipuri demo (cameră fixă, oameni prin fața panoului), cifre cost/valoare, prezentarea de 3 minute | baza de date completă, clipurile alese, slide-urile și pitch-ul repetat | `content` | _liber_ |

Dependențe: **3** poate începe imediat cu videoclipurile existente din `output/`. **2** are nevoie de formatul `ads.json` (de mai jos) pentru textul reclamelor; până e gata baza de date, folosește exemplul din contract. **1** leagă totul la final; până atunci fiecare task rulează singur, pe fișiere.

## Reclamele: reclame reale ale brandurilor + AI care adaptează formatul (decizie de echipă)

- Folosim **reclame reale** ale unor branduri cunoscute din fiecare țară (ex. Pizza Hut). Nu le facem noi.
- **Produsul și reclama rămân cele reale.** AI-ul nu inventează produse și nu schimbă mesajul brandului.
- Problema pe care o rezolvă AI-ul: reclama reală vine într-un singur format, dar trebuie să încapă pe suprafețe foarte diferite (în clipul de test: panou vertical 0,74, firmă 1,55, autobuz 2,92). AI-ul extinde sau recompune **fundalul** din jurul reclamei ca să se potrivească formatului, fără să o deformeze.
- În prezentare: mențiunea *„Branduri folosite strict demonstrativ, fără afiliere”*. Videoclipurile cu branduri reale nu se publică online.
- API de imagini: Firefly nu e disponibil. Încercăm întâi **Gemini** (cheie în `.env` ca `GEMINI_API_KEY`), apoi Replicate/FLUX. Furnizorul trebuie să fie interschimbabil.
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

**`output/<clip>.manifest.json`** (task 1 → task 3)
```json
{ "clip": "melbourne", "ai_view": "output/melbourne_ai_view.mp4",
  "regions": [ { "code": "RO", "label": "România", "video": "output/melbourne_ro.mp4",
                 "ad_id": "ro-pizza-hut", "reason": "..." } ] }
```

## Cum rulezi (o singură comandă)

```bash
python -m venv .venv          # sau: python -m uv venv .venv
.venv/Scripts/pip install -r requirements.txt     # Windows; pe Mac/Linux: .venv/bin/pip
# reclamele reale nu sunt în git: descarcă fiecare `creative` din data/ads.json de la `creative_source`
.venv/Scripts/python.exe pipeline/run.py assets/clips/melbourne.mp4 --max-frames 480
```

`run.py` face tot lanțul: detectare AI (dacă nu există deja `output/<clip>.surfaces.json`), alegerea reclamei pe țară, adaptarea la formatul suprafeței, randarea tuturor țărilor + „AI view” + video comparativ, apoi scrie `output/<clip>.manifest.json`.

Folosește automat ce produc celelalte task-uri, dacă există, altfel are fallback sigur:
- `data/ads.json` (task 4): **obligatoriu**, doar reclame reale; implicit se randează fiecare regiune care are o reclamă acolo
- `output/<clip>.scene.json` (task 2) pentru alegerea AI și motiv; fără el: primul brand al regiunii
- `assets/generated/<clip>/<regiune>.png` (task 2) pentru reclama adaptată de AI; fără el: `adapt_ad.py` încadrează reclama fără deformare

Clipul de test nu e în git (prea mare). Se descarcă de pe [Pexels](https://www.pexels.com/video/people-walking-down-a-city-street-with-a-red-jacket-27817664/) și se salvează ca `assets/clips/melbourne.mp4`.

| Script | Rol |
|---|---|
| `pipeline/run.py` | **comanda principală:** tot lanțul, de la clip la `manifest.json` |
| `pipeline/adapt_ad.py` | încadrează o reclamă la formatul suprafeței fără deformare (fallback pentru AI-ul din task 2) |
| `pipeline/insert_ad.py` | motorul: urmărire (optical flow + omografie), pierdere și regăsire (SIFT), oameni în față (YOLO-seg), export pe țări + „AI view” |
| `pipeline/detect_surfaces.py` | **AI:** găsește singur suprafețele publicitare (OWLv2 + SAM 2) și scrie `surfaces.json`; `insert_ad.py --corners` îl acceptă direct |
| `pipeline/pick_corners.py` | marcare manuală a colțurilor (fallback dacă detectorul greșește) |
| `pipeline/side_by_side.py` | video cu țările una lângă alta, sincronizate |
| `pipeline/contact_sheet.py` | imagine cu cadre-cheie pentru verificare rapidă |

## Reguli de lucru

- **Nu lucrăm direct pe `main`.** Branch-ul tău, apoi Pull Request.
- `git pull` des. Commit-uri mici, cu mesaje clare.
- **Nu urcăm** videoclipuri, `output/`, greutăți de modele (`*.pt`) sau `.env`; sunt în `.gitignore`.
- **Cheile API** stau doar în `.env` (ex. `IMAGE_API_KEY=...`), niciodată în cod, chat sau commit.
- Reclame **reale** de branduri, folosite doar demonstrativ (cu mențiunea de neafiliere în prezentare); clipurile video doar cu licență liberă (Pexels).

## Note pentru Claude Code

- Mediu de dezvoltare: Windows, Python 3.14 în `.venv`, GPU RTX 3060 6 GB (PyTorch e momentan pe CPU), Ollama local cu `gemma3:4b`.
- Optimizează pentru demo: fallback-uri sigure (ex. rezultate pre-randate) în loc de funcții fragile.
- Respectă contractele JSON de mai sus. Dacă trebuie schimbate, actualizează și acest fișier.
- Limite cunoscute ale motorului: urmărirea poate aluneca la mișcări foarte bruște; reclama e puțin prea „curată” față de scenă (de îmbunătățit armonizarea); ~0,7 s/cadru pe CPU.
