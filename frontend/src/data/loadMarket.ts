import type { Bid, Slot } from "./types";
import { assetUrl } from "./loadClip";
import mockInventory from "./mock/inventory.json";
import mockBids from "./mock/bids.json";

async function fetchList<T>(path: string): Promise<T[] | undefined> {
  try {
    const res = await fetch(assetUrl(path), { cache: "no-store" });
    if (!res.ok) return undefined;
    const data = await res.json();
    return Array.isArray(data) ? (data as T[]) : undefined;
  } catch {
    return undefined;
  }
}

/** data/inventory.json și data/bids.json dacă există în repo, altfel datele de test. */
export async function loadMarket(): Promise<{ slots: Slot[]; bids: Bid[] }> {
  const [slots, bids] = await Promise.all([fetchList<Slot>("data/inventory.json"), fetchList<Bid>("data/bids.json")]);
  return {
    slots: slots ?? (mockInventory as Slot[]),
    bids: bids ?? (mockBids as Bid[]),
  };
}
