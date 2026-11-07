// Spațiile de vânzare și ofertele: din backend (/api/placements) dacă rulează, apoi data/*.json, apoi datele de test.
import type { Ad, Bid, Slot } from "./types";
import { apiAvailable, assetUrl } from "./loadClip";
import mockInventory from "./mock/inventory.json";
import mockBids from "./mock/bids.json";

export interface MarketData {
  slots: Slot[];
  bids: Bid[];
  /** companiile care au licitat prin backend (nu sunt în ads.json) */
  companies: Ad[];
  source: "api" | "files" | "mock";
  /** backend-ul răspunde, dar n-are încă nicio ofertă: arătăm datele de test până apare prima */
  waitingForBids?: boolean;
}

async function fetchJson<T>(path: string): Promise<T | undefined> {
  try {
    const res = await fetch(assetUrl(path), { cache: "no-store" });
    if (!res.ok) return undefined;
    return (await res.json()) as T;
  } catch {
    return undefined;
  }
}

/** GET /api/placements (backend/outreach/bids.py) */
interface ApiPlacement {
  id: string;
  clip: string;
  /** locul de reclamă din film (s1, s2...); id-ul e clip:suprafață:ȚARĂ */
  surface_id?: string;
  market: string;
  market_name?: string;
  floor_usd: number;
  expected_views: number;
  cpm_usd: number;
  bids: number;
}

/** GET /api/placements/{id}/bids */
interface ApiBid {
  id: number;
  company: string;
  amount_usd: number;
  message?: string;
  created: number;
}

const companyId = (market: string, company: string) => `co:${market}:${company.trim().toLowerCase()}`;

async function loadFromApi(): Promise<MarketData | undefined> {
  const placements = await fetchJson<ApiPlacement[]>("api/placements");
  if (!placements?.length) return undefined;

  const slots: Slot[] = placements.map((p) => ({
    id: p.id,
    clip: p.clip,
    surface_id: p.surface_id ?? "s1",
    region: p.market,
    title: `${p.clip.charAt(0).toUpperCase()}${p.clip.slice(1)}, ad place ${(p.surface_id ?? "s1").replace(/^s/, "")}`,
    audience: p.expected_views,
    cpm: p.cpm_usd,
    currency: "USD",
    floor: p.floor_usd,
    status: "open",
  }));

  const withBids = placements.filter((p) => p.bids > 0);
  const lists = await Promise.all(withBids.map((p) => fetchJson<ApiBid[]>(`api/placements/${encodeURIComponent(p.id)}/bids`)));
  const bids: Bid[] = [];
  const companies = new Map<string, Ad>();
  withBids.forEach((p, i) => {
    for (const b of lists[i] ?? []) {
      const name = b.company?.trim() || "Unnamed business";
      const id = companyId(p.market, name);
      companies.set(id, { id, region: p.market, brand: name });
      bids.push({
        id: `api-${b.id}`,
        slot_id: p.id,
        brand_id: id,
        amount: b.amount_usd,
        placed_at: new Date(b.created * 1000).toISOString(),
        message: b.message || undefined,
      });
    }
  });
  return { slots, bids, companies: [...companies.values()], source: "api" };
}

export async function loadMarket(): Promise<MarketData> {
  let waitingForBids = false;
  if (await apiAvailable()) {
    const api = await loadFromApi();
    // un backend fără nicio ofertă ar lăsa Marketplace și Companies goale: până la prima ofertă reală, datele de test
    if (api?.bids.length) return api;
    waitingForBids = !!api;
  }
  const [slots, bids] = await Promise.all([fetchJson<Slot[]>("data/inventory.json"), fetchJson<Bid[]>("data/bids.json")]);
  if (Array.isArray(slots) && Array.isArray(bids)) return { slots, bids, companies: [], source: "files", waitingForBids };
  return { slots: mockInventory as Slot[], bids: mockBids as Bid[], companies: [], source: "mock", waitingForBids };
}
