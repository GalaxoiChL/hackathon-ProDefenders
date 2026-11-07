# Frontend plan (Task 3)

> Working document: change it as we go. `CLAUDE.md` stays the source of truth for the idea and the JSON contracts.

## Direction

A customer-facing product in the spirit of Mirriad (virtual product placement), not an AI tech demo:
- **Viewers** watch one scene with the billboard localised to their country.
- **Brands** bid for billboards in a marketplace and track how they perform.

Look: classic, editorial, "human-made". Off-white paper, near-black ink, one oxblood accent, serif headings (Fraunces) with Inter for UI, thin rules, no gradients, glows or decorative badges. Motion is quiet: 200–300 ms fades, sliding underlines and selection bars, cross-fades between countries, count-up numbers, a line chart that draws itself. All of it respects "reduce motion".

## Tabs

| Tab | For | What it does |
|---|---|---|
| **Watch** | viewers | Video selector + country selector; all country versions play in sync so switching never restarts; "Show what the AI sees" toggle; the ad on the billboard and why the AI chose it |
| **Compare** | everyone | All countries side by side with one shared transport; before/after wipe slider (original vs. one country) |
| **Marketplace** | brands | Placements (clip × billboard × country) with minimum price; sealed bids with eligibility checks (market, category, brand safety, minimum); countdown; second-price result with reasons |
| **Companies** | brands | Per-company stats (won, win rate, spend, impressions, CPM, visibility), 14-day impressions chart, bid history, comparison table |

Tabs live in `src/tabs.config.ts`; reorder or hide them there.

## Data

Sources, in order (see `src/data/loadClip.ts`; the footer shows which one is in use):
1. **Backend API** (`backend` branch, `uvicorn backend.app:app --port 8000`). In dev, Vite proxies `/api` to it (`BACKEND_URL` to change). Uses `/api/clips`, `/api/clips/{clip}`, `/scene`, `/surfaces`, `/stats`, `/play` (viewer country from IP) and `/api/ads`.
2. **Files** in `output/` written by `pipeline/run.py` (`video-pipeline` branch); both manifest shapes are normalised.
3. **Sample data** in `src/data/mock/`.

Videos are served in 4 MB range chunks in dev, because browsers allow only 6 connections per server and Compare plays up to 6 videos at once. The backend serves whole files, so the same limit applies there.

| File | Owner | Status |
|---|---|---|
| `output/<clip>.manifest.json` | Task 1 | in `CLAUDE.md`; optional fields (`metrics`, `original`, `stats`) proposed |
| `data/ads.json` | Task 4 | in `CLAUDE.md`; used as the list of companies |
| `data/inventory.json` (placements) | Task 4 | **new, to add to `CLAUDE.md`**; shape = `Slot` in `src/data/types.ts` |
| `data/bids.json` | Task 4 | **new, to add to `CLAUDE.md`**; shape = `Bid` in `src/data/types.ts` |

Every file falls back to sample data in `src/data/mock/` when missing; the footer says which is in use. Auction rules live in `src/data/auction.ts` (minimum price formula, eligibility, second price).

Open question for the team: for the auction winner to really appear in Watch, the pipeline must pre-render one video per candidate brand, not just one per country.

## Where to change things

| What | Where |
|---|---|
| Tabs | `src/tabs.config.ts` |
| Colours, fonts | `src/styles/theme.css` |
| Country colours and names | `src/regions.ts` |
| Auction rules | `src/data/auction.ts` |
| Sample data | `src/data/mock/` |

## Next

1. Real footage from `output/` (ask Task 1) and check sync on the presentation laptop.
2. Agree `inventory.json` / `bids.json` with Task 4 and add them to `CLAUDE.md`.
3. IP geolocation to preselect the viewer's country.
4. Polish: empty and error states, presentation-screen test, PR to `main`.

Run: `cd frontend && npm install && npm run dev` → http://localhost:5173
