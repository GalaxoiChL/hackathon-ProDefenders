import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useApp } from "./state";
import { loadMarket, type MarketData } from "./data/loadMarket";
import { ineligibility, runAuction, type AuctionResult } from "./data/auction";
import type { Ad, Bid, Slot } from "./data/types";
import mockAds from "./data/mock/ads.json";

/** Cât de des reîncărcăm ofertele din backend (vin prin linkurile din emailuri). */
const API_REFRESH_MS = 15_000;

interface MarketState {
  slots: Slot[];
  bids: Bid[];
  brands: Ad[];
  source: MarketData["source"] | null;
  /** backend-ul rulează, dar n-are oferte: se văd datele de test */
  waitingForBids: boolean;
  /** moneda spațiilor (toate au aceeași în aceeași sursă) */
  currency: Slot["currency"];
  /** Momentul (ms) la care se închide fiecare licitație deschisă. */
  deadlines: Record<string, number>;
  isClosed: (slotId: string) => boolean;
  results: Record<string, AuctionResult>;
  /** Întoarce motivul refuzului, sau null dacă oferta a fost acceptată. */
  placeBid: (slotId: string, brandId: string, amount: number) => string | null;
  /** Ofertă deschisă, fără backend: orice firmă (nu doar cele din ads.json); null dacă a fost acceptată. */
  placeOpenBid: (slotId: string, company: string, category: string, amount: number) => string | null;
  closeAuction: (slotId: string) => void;
}

const MarketContext = createContext<MarketState | null>(null);

export function MarketProvider({ children }: { children: ReactNode }) {
  const loaded = useApp().data?.ads;
  const [market, setMarket] = useState<MarketData | null>(null);
  const [bids, setBids] = useState<Bid[]>([]);
  const [deadlines, setDeadlines] = useState<Record<string, number>>({});
  const [closed, setClosed] = useState<Set<string>>(new Set());
  /** firmele care au licitat din Marketplace fără backend (nu sunt în ads.json) */
  const [walkIns, setWalkIns] = useState<Ad[]>([]);
  const slots = useMemo(() => market?.slots ?? [], [market]);

  // Companiile: cu backend, reclamele lui + cine a licitat prin el; cu datele de test, doar brandurile de test,
  // ca Marketplace și Companies să arate la fel pe orice laptop.
  const brands = useMemo(() => {
    const byId = new Map<string, Ad>();
    const all =
      market?.source === "api"
        ? [...(loaded ?? []), ...market.companies]
        : market?.source === "files"
          ? [...(loaded ?? []), ...(mockAds as Ad[])]
          : (mockAds as Ad[]);
    for (const a of [...all, ...walkIns]) if (!byId.has(a.id)) byId.set(a.id, a);
    return [...byId.values()];
  }, [loaded, market, walkIns]);

  /** Pornește de la zero cu o sursă nouă (prima încărcare, sau trecerea de la datele de test la backend). */
  const start = useCallback((m: MarketData) => {
    const now = Date.now();
    setMarket(m);
    setBids(m.bids);
    setDeadlines(Object.fromEntries(m.slots.filter((s) => s.closes_in_sec).map((s) => [s.id, now + s.closes_in_sec! * 1000])));
    setClosed(new Set(m.slots.filter((s) => s.status === "closed" || (!s.status && !s.closes_in_sec)).map((s) => s.id)));
  }, []);

  useEffect(() => {
    loadMarket().then(start);
  }, [start]);

  // ofertele din backend sosesc oricând (pagina /bid/<token> din email): le reîncărcăm periodic, iar la prima
  // ofertă reală trecem de la datele de test la cele din backend
  const watching = market?.source === "api" || !!market?.waitingForBids;
  const source = useRef(market?.source);
  source.current = market?.source;
  useEffect(() => {
    if (!watching) return;
    const t = window.setInterval(() => {
      loadMarket().then((m) => {
        if (m.source !== "api") return; // tot fără oferte: rămânem pe datele de test
        if (source.current !== "api") return start(m);
        setMarket(m);
        setBids(m.bids);
      });
    }, API_REFRESH_MS);
    return () => clearInterval(t);
  }, [watching, start]);

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
        { id: `u${Date.now()}`, slot_id: slotId, brand_id: brandId, amount, placed_at: new Date().toISOString() },
      ]);
      return null;
    },
    [slots, brands, closed],
  );

  const placeOpenBid = useCallback(
    (slotId: string, company: string, category: string, amount: number) => {
      const slot = slots.find((s) => s.id === slotId);
      const name = company.trim();
      if (!slot || closed.has(slotId)) return "This auction is closed";
      if (name.length < 2) return "Enter your company name";
      if (!Number.isFinite(amount) || amount <= 0) return "Enter an amount";
      const id = `walkin:${slot.region}:${name.toLowerCase()}`;
      const brand: Ad = { id, region: slot.region, brand: name, category: category || undefined };
      const reason = ineligibility(slot, brand, amount);
      if (reason) return reason;
      setWalkIns((list) => (list.some((b) => b.id === id) ? list : [...list, brand]));
      setBids((list) => [
        ...list.filter((b) => !(b.slot_id === slotId && b.brand_id === id)),
        { id: `u${Date.now()}`, slot_id: slotId, brand_id: id, amount, placed_at: new Date().toISOString() },
      ]);
      return null;
    },
    [slots, closed],
  );

  const value: MarketState = {
    slots,
    bids,
    brands,
    source: market?.source ?? null,
    waitingForBids: !!market?.waitingForBids,
    currency: slots[0]?.currency ?? "EUR",
    deadlines,
    isClosed: (id) => closed.has(id),
    results,
    placeBid,
    placeOpenBid,
    closeAuction,
  };
  return <MarketContext.Provider value={value}>{children}</MarketContext.Provider>;
}

export function useMarket(): MarketState {
  const ctx = useContext(MarketContext);
  if (!ctx) throw new Error("useMarket must be used inside <MarketProvider>");
  return ctx;
}
