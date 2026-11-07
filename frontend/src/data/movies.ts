// Marketplace-ul de filme: fiecare clip e un film, fiecare panou din el e un loc de reclamă,
// iar fiecare loc se vinde separat în fiecare țară. Din backend (/api/movies) sau, fără server,
// construit din datele de test ale Marketplace-ului (market.tsx).
import type { Ad, Bid, Slot } from "./types";
import { reservePrice } from "./auction";

export type Currency = "EUR" | "USD";

/** Un loc de reclamă într-o țară: ce cumpără o firmă. */
export interface Offer {
  id: string;
  clip: string;
  surface_id: string;
  market: string;
  floor: number;
  currency: Currency;
  expected_views: number;
  cpm: number;
  bids: number;
  top_bid?: number;
  status: "open" | "closed";
  /** categoriile acceptate de proprietarul filmului (doar în datele de test) */
  categories?: string[];
}

/** Un loc de reclamă din film (un panou, afiș sau ecran detectat de AI). */
export interface Place {
  id: string;
  label: string;
  type: string;
  confidence?: number;
  frame_share_pct?: number;
  image_url?: string;
  bids: number;
  top_bid?: number;
  offers: Offer[];
}

export interface Movie {
  clip: string;
  title: string;
  subtitle?: string;
  thumbnail_url?: string;
  video_url?: string;
  duration_s?: number;
  places: Place[];
  markets: string[];
  bids: number;
  top_bid?: number;
  min_floor?: number;
  currency: Currency;
}

export interface PublicBid {
  id: string;
  company: string;
  amount: number;
  message?: string;
  placed_at: string;
}

export interface BidForm {
  company: string;
  email: string;
  category: string;
  amount: number;
  message: string;
}

export type BidResult = { ok: true; rank: number; leading: boolean } | { ok: false; error: string };

export const CATEGORIES = ["food", "drinks", "coffee", "retail", "beauty", "fitness", "hotel", "electronics", "services"];

// ---------------- backend ----------------
interface ApiOffer {
  id: string;
  clip: string;
  surface_id: string;
  market: string;
  floor_usd: number;
  expected_views: number;
  cpm_usd: number;
  bids: number;
  top_bid_usd: number | null;
}
interface ApiPlace {
  id: string;
  label: string;
  type: string;
  confidence: number | null;
  frame_share_pct: number | null;
  image_url: string | null;
  bids: number;
  top_bid_usd: number | null;
  offers: ApiOffer[];
}
interface ApiMovie {
  clip: string;
  title: string;
  thumbnail_url: string | null;
  video_url: string | null;
  duration_s: number | null;
  scene: { location?: string; time_of_day?: string; weather?: string; mood?: string } | null;
  places: number | ApiPlace[];
  markets: string[];
  bids: number;
  top_bid_usd: number | null;
  min_floor_usd: number | null;
}

const opt = <T,>(v: T | null | undefined) => (v === null ? undefined : v);

const offerFromApi = (o: ApiOffer): Offer => ({
  id: o.id,
  clip: o.clip,
  surface_id: o.surface_id,
  market: o.market,
  floor: o.floor_usd,
  currency: "USD",
  expected_views: o.expected_views,
  cpm: o.cpm_usd,
  bids: o.bids,
  top_bid: opt(o.top_bid_usd),
  status: "open",
});

function movieFromApi(m: ApiMovie): Movie {
  const places = Array.isArray(m.places)
    ? m.places.map((p) => ({
        id: p.id,
        label: p.label,
        type: p.type,
        confidence: opt(p.confidence),
        frame_share_pct: opt(p.frame_share_pct),
        image_url: opt(p.image_url),
        bids: p.bids,
        top_bid: opt(p.top_bid_usd),
        offers: p.offers.map(offerFromApi),
      }))
    : Array.from({ length: m.places }, (_, i) => ({ id: `s${i + 1}`, label: `Ad place ${i + 1}`, type: "", bids: 0, offers: [] }));
  const sc = m.scene;
  return {
    clip: m.clip,
    title: m.title,
    subtitle: sc ? [sc.location, sc.time_of_day, sc.weather].filter(Boolean).join(" · ") : undefined,
    thumbnail_url: opt(m.thumbnail_url),
    video_url: opt(m.video_url),
    duration_s: opt(m.duration_s),
    places,
    markets: m.markets,
    bids: m.bids,
    top_bid: opt(m.top_bid_usd),
    min_floor: opt(m.min_floor_usd),
    currency: "USD",
  };
}

async function getJson<T>(path: string): Promise<T | undefined> {
  try {
    const r = await fetch(path, { cache: "no-store" });
    return r.ok ? ((await r.json()) as T) : undefined;
  } catch {
    return undefined;
  }
}

export async function fetchMovies(): Promise<Movie[] | undefined> {
  const list = await getJson<ApiMovie[]>("/api/movies");
  return list?.map(movieFromApi);
}

export async function fetchMovie(clip: string): Promise<Movie | undefined> {
  const m = await getJson<ApiMovie>(`/api/movies/${encodeURIComponent(clip)}`);
  return m && movieFromApi(m);
}

export async function fetchBids(offerId: string): Promise<PublicBid[]> {
  const list = await getJson<{ id: number; company: string; amount_usd: number; message?: string; created: number }[]>(
    `/api/placements/${encodeURIComponent(offerId)}/bids`,
  );
  return (list ?? []).map((b) => ({
    id: String(b.id),
    company: b.company || "Unnamed business",
    amount: b.amount_usd,
    message: b.message || undefined,
    placed_at: new Date(b.created * 1000).toISOString(),
  }));
}

export async function postBid(offerId: string, form: BidForm): Promise<BidResult> {
  try {
    const r = await fetch(`/api/placements/${encodeURIComponent(offerId)}/bids`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        company: form.company,
        email: form.email,
        amount_usd: form.amount,
        category: form.category || undefined,
        message: form.message || undefined,
      }),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) {
      const detail = Array.isArray(d.detail) ? d.detail[0]?.msg : d.detail;
      return { ok: false, error: detail ? String(detail) : `Server error (${r.status})` };
    }
    return { ok: true, rank: d.rank, leading: d.leading };
  } catch {
    return { ok: false, error: "The server did not answer. Try again." };
  }
}

// ---------------- sample data (no server) ----------------
const titleCase = (s: string) => s.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

/** Filmele construite din spațiile de test: grupate pe clip, apoi pe suprafață. */
export function moviesFromSlots(slots: Slot[], bids: Bid[], isClosed: (id: string) => boolean): Movie[] {
  const byClip = new Map<string, Slot[]>();
  for (const s of slots) byClip.set(s.clip, [...(byClip.get(s.clip) ?? []), s]);
  return [...byClip.entries()].map(([clip, list]) => {
    const bySurface = new Map<string, Slot[]>();
    for (const s of list) bySurface.set(s.surface_id, [...(bySurface.get(s.surface_id) ?? []), s]);
    const places: Place[] = [...bySurface.entries()]
      .sort(([a], [b]) => a.localeCompare(b, undefined, { numeric: true }))
      .map(([sid, ss], i) => {
        const offers: Offer[] = ss.map((s) => {
          const mine = bids.filter((b) => b.slot_id === s.id);
          return {
            id: s.id,
            clip,
            surface_id: sid,
            market: s.region,
            floor: reservePrice(s),
            currency: s.currency,
            expected_views: s.audience,
            cpm: s.cpm,
            bids: mine.length,
            top_bid: mine.length ? Math.max(...mine.map((b) => b.amount)) : undefined,
            status: isClosed(s.id) ? "closed" : "open",
            categories: s.categories,
          };
        });
        const tops = offers.map((o) => o.top_bid ?? 0);
        return {
          id: sid,
          label: `Ad place ${i + 1}`,
          type: ss[0].title.split(",")[1]?.trim() ?? "billboard",
          bids: offers.reduce((n, o) => n + o.bids, 0),
          top_bid: Math.max(0, ...tops) || undefined,
          image_url: ss[0].thumbnail,
          offers,
        };
      });
    const offers = places.flatMap((p) => p.offers);
    return {
      clip,
      title: titleCase(clip),
      subtitle: list[0].title.split(",")[0],
      thumbnail_url: list.find((s) => s.thumbnail)?.thumbnail,
      places,
      markets: [...new Set(offers.map((o) => o.market))],
      bids: offers.reduce((n, o) => n + o.bids, 0),
      top_bid: Math.max(0, ...offers.map((o) => o.top_bid ?? 0)) || undefined,
      min_floor: Math.min(...offers.map((o) => o.floor)),
      currency: list[0].currency,
    };
  });
}

/** Ofertele de test pentru un spațiu, cu numele companiilor. */
export function sampleBids(offerId: string, bids: Bid[], brands: Ad[]): PublicBid[] {
  return bids
    .filter((b) => b.slot_id === offerId)
    .sort((a, b) => b.amount - a.amount)
    .map((b) => ({
      id: b.id,
      company: brands.find((x) => x.id === b.brand_id)?.brand ?? b.brand_id,
      amount: b.amount,
      message: b.message,
      placed_at: b.placed_at,
    }));
}
