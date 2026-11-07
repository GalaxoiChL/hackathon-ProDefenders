import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useApp } from "./state";
import { loadMarket } from "./data/loadMarket";
import { ineligibility, runAuction, type AuctionResult } from "./data/auction";
import type { Ad, Bid, Slot } from "./data/types";

interface MarketState {
  slots: Slot[];
  bids: Bid[];
  brands: Ad[];
  /** Momentul (ms) la care se închide fiecare licitație deschisă. */
  deadlines: Record<string, number>;
  isClosed: (slotId: string) => boolean;
  results: Record<string, AuctionResult>;
  /** Întoarce motivul refuzului, sau null dacă oferta a fost acceptată. */
  placeBid: (slotId: string, brandId: string, amount: number) => string | null;
  closeAuction: (slotId: string) => void;
}

const MarketContext = createContext<MarketState | null>(null);

export function MarketProvider({ children }: { children: ReactNode }) {
  const brands = useApp().data?.ads ?? [];
  const [slots, setSlots] = useState<Slot[]>([]);
  const [bids, setBids] = useState<Bid[]>([]);
  const [deadlines, setDeadlines] = useState<Record<string, number>>({});
  const [closed, setClosed] = useState<Set<string>>(new Set());

  useEffect(() => {
    loadMarket().then(({ slots, bids }) => {
      const now = Date.now();
      setSlots(slots);
      setBids(bids);
      setDeadlines(Object.fromEntries(slots.filter((s) => s.closes_in_sec).map((s) => [s.id, now + s.closes_in_sec! * 1000])));
      setClosed(new Set(slots.filter((s) => !s.closes_in_sec).map((s) => s.id)));
    });
  }, []);

  const closeAuction = useCallback((slotId: string) => setClosed((c) => new Set(c).add(slotId)), []);

  // închide automat licitațiile când expiră timpul
  useEffect(() => {
    const timers = Object.entries(deadlines)
      .filter(([id]) => !closed.has(id))
      .map(([id, at]) => window.setTimeout(() => closeAuction(id), Math.max(0, at - Date.now())));
    return () => timers.forEach(clearTimeout);
  }, [deadlines, closed, closeAuction]);

  const results = useMemo(() => {
    const out: Record<string, AuctionResult> = {};
    for (const s of slots) {
      if (closed.has(s.id)) out[s.id] = runAuction(s, bids.filter((b) => b.slot_id === s.id), brands);
    }
    return out;
  }, [slots, bids, brands, closed]);

  const placeBid = useCallback(
    (slotId: string, brandId: string, amount: number) => {
      const slot = slots.find((s) => s.id === slotId);
      if (!slot || closed.has(slotId)) return "This auction is closed";
      if (!Number.isFinite(amount) || amount <= 0) return "Enter an amount";
      const reason = ineligibility(slot, brands.find((b) => b.id === brandId), amount);
      if (reason) return reason;
      setBids((list) => [
        ...list.filter((b) => !(b.slot_id === slotId && b.brand_id === brandId)), // o ofertă nouă o înlocuiește pe cea veche
        { id: `u${Date.now()}`, slot_id: slotId, brand_id: brandId, amount_eur: amount, placed_at: new Date().toISOString() },
      ]);
      return null;
    },
    [slots, brands, closed],
  );

  const value: MarketState = {
    slots,
    bids,
    brands,
    deadlines,
    isClosed: (id) => closed.has(id),
    results,
    placeBid,
    closeAuction,
  };
  return <MarketContext.Provider value={value}>{children}</MarketContext.Provider>;
}

export function useMarket(): MarketState {
  const ctx = useContext(MarketContext);
  if (!ctx) throw new Error("useMarket must be used inside <MarketProvider>");
  return ctx;
}
