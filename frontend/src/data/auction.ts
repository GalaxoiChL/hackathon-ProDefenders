// Regulile licitației, deterministe: AI-ul măsoară scena, banii și câștigătorul se calculează aici.
import type { Ad, Bid, Slot } from "./types";

/**
 * Preț minim: cel dat de backend (CPM × privitori / 1000), altfel
 * audiență/1000 × CPM × expunere × vizibilitate, cu expunerea plafonată la 1,5 (15 s pe ecran).
 */
export function reservePrice(slot: Slot): number {
  if (slot.floor !== undefined) return slot.floor;
  const exposure = Math.min((slot.screen_time_sec ?? 10) / 10, 1.5);
  return Math.round((slot.audience / 1000) * slot.cpm * exposure * ((slot.visibility ?? 10) / 10));
}

/** Cum s-a calculat prețul minim, ca text pentru interfață. */
export const reserveFormula = (slot: Slot) =>
  slot.floor !== undefined ? "Minimum = CPM × expected views ÷ 1,000." : "Minimum = audience ÷ 1,000 × CPM × exposure × visibility.";

/** Motivul pentru care o ofertă nu poate câștiga, sau null dacă e eligibilă. */
export function ineligibility(slot: Slot, brand: Ad | undefined, amount: number): string | null {
  if (!brand) return "Unknown company";
  if (brand.region !== slot.region) return `Not active in ${slot.region}`;
  if (slot.categories?.length && !slot.categories.includes(brand.category ?? "")) {
    return `Category “${brand.category}” is not accepted in this scene`;
  }
  const clash = brand.avoid?.find((t) => slot.tags?.includes(t));
  if (clash) return `Brand safety: the brand avoids “${clash}” scenes`;
  if (amount < reservePrice(slot)) return "Below the minimum price";
  return null;
}

export interface BidOutcome {
  bid: Bid;
  status: "won" | "lost" | "rejected";
  reason?: string;
}

export interface AuctionResult {
  outcomes: BidOutcome[];
  winner?: Bid;
  /** Second-price: câștigătorul plătește a doua ofertă eligibilă, dar cel puțin prețul minim. */
  price?: number;
}

const RANK = { won: 0, lost: 1, rejected: 2 } as const;

export function runAuction(slot: Slot, bids: Bid[], brands: Ad[]): AuctionResult {
  const byId = new Map(brands.map((b) => [b.id, b]));
  const outcomes: BidOutcome[] = bids.map((bid) => {
    const reason = ineligibility(slot, byId.get(bid.brand_id), bid.amount);
    return reason ? { bid, status: "rejected", reason } : { bid, status: "lost" };
  });
  const eligible = outcomes
    .filter((o) => o.status !== "rejected")
    .sort((a, b) => b.bid.amount - a.bid.amount || a.bid.placed_at.localeCompare(b.bid.placed_at));

  const sorted = () => [...outcomes].sort((a, b) => RANK[a.status] - RANK[b.status] || b.bid.amount - a.bid.amount);
  if (!eligible.length) return { outcomes: sorted() };

  eligible[0].status = "won";
  for (const o of eligible.slice(1)) o.reason = "Outbid";
  const price = Math.max(reservePrice(slot), eligible[1]?.bid.amount ?? 0);
  return { outcomes: sorted(), winner: eligible[0].bid, price };
}
