import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useMarket } from "../market";
import type { AuctionResult } from "../data/auction";
import type { Ad, Bid, Slot } from "../data/types";
import { AdCreative, CountryMark, PageHeader, Section, Stat, compact, dec, money, num, pct } from "../components/ui";

interface CompanyStats {
  brand: Ad;
  bids: Bid[];
  /** Ofertele din licitații deja închise. */
  decided: number;
  won: { slot: Slot; bid: Bid; price: number }[];
  spend: number;
  impressions: number;
  cpm?: number;
  winRate?: number;
  avgVisibility?: number;
}

function computeStats(brand: Ad, slots: Slot[], bids: Bid[], results: Record<string, AuctionResult>): CompanyStats {
  const own = bids.filter((b) => b.brand_id === brand.id);
  const decided = own.filter((b) => results[b.slot_id]).length;
  const won = own.flatMap((bid) => {
    const r = results[bid.slot_id];
    const slot = slots.find((s) => s.id === bid.slot_id);
    return r?.winner?.id === bid.id && slot && r.price !== undefined ? [{ slot, bid, price: r.price }] : [];
  });
  const spend = won.reduce((s, w) => s + w.price, 0);
  const impressions = won.reduce((s, w) => s + w.slot.audience, 0);
  return {
    brand,
    bids: own,
    decided,
    won,
    spend,
    impressions,
    cpm: impressions ? (spend / impressions) * 1000 : undefined,
    winRate: decided ? won.length / decided : undefined,
    avgVisibility: (() => {
      const v = won.map((w) => w.slot.visibility).filter((x): x is number => x !== undefined);
      return v.length ? v.reduce((a, b) => a + b, 0) / v.length : undefined;
    })(),
  };
}

export default function CompaniesTab() {
  const { brands, slots, bids, results, currency } = useMarket();
  const cash = (n: number) => money(n, currency);
  const stats = brands
    .map((b) => computeStats(b, slots, bids, results))
    .sort((a, b) => b.spend - a.spend || b.bids.length - a.bids.length || a.brand.brand.localeCompare(b.brand.brand));
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = stats.find((s) => s.brand.id === selectedId) ?? stats[0];

  return (
    <>
      <PageHeader
        eyebrow="For brands"
        title="Companies"
        lede="How every brand performs on the marketplace: what it bid, what it won, what it paid and who saw it. Audience and impression figures are simulated for the prototype."
      />

      <div className="grid gap-x-6 gap-y-3 sm:grid-cols-3 lg:grid-cols-4">
        {stats.filter((s) => s.bids.length > 0).map((s) => {
          const active = s.brand.id === selected?.brand.id;
          return (
            <button
              key={s.brand.id}
              onClick={() => setSelectedId(s.brand.id)}
              aria-pressed={active}
              className={`relative border-t pt-3 pb-1 text-left transition-colors ${active ? "border-transparent" : "border-rule hover:border-rule-strong"}`}
            >
              {active && <motion.span layoutId="company-rule" className="absolute inset-x-0 -top-px h-[3px] bg-ink" transition={{ duration: 0.3, ease: [0.2, 0.7, 0.2, 1] }} />}
              <p className={`font-serif text-lg ${active ? "" : "text-ink-2"}`}>{s.brand.brand}</p>
              <p className="mt-0.5 flex items-center justify-between gap-2 text-xs text-muted">
                <CountryMark code={s.brand.region} muted />
                <span className="tabular-nums">{s.spend ? cash(s.spend) : "no spend"}</span>
              </p>
            </button>
          );
        })}
      </div>

      <AnimatePresence mode="wait">
        {selected && (
          <motion.div key={selected.brand.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.22 }}>
            <CompanyDetail s={selected} />
          </motion.div>
        )}
      </AnimatePresence>

      <Section title="All companies" aside="Sorted by spend">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr className="border-b border-ink text-left text-xs uppercase tracking-[0.12em] text-muted">
                <th className="py-2 font-medium">Company</th>
                <th className="py-2 font-medium">Market</th>
                <th className="py-2 text-right font-medium">Bids</th>
                <th className="py-2 text-right font-medium">Won</th>
                <th className="py-2 text-right font-medium">Win rate</th>
                <th className="py-2 text-right font-medium">Spend</th>
                <th className="py-2 text-right font-medium">Impressions</th>
                <th className="py-2 text-right font-medium">CPM</th>
              </tr>
            </thead>
            <tbody>
              {stats.map((s) => (
                <tr
                  key={s.brand.id}
                  onClick={() => setSelectedId(s.brand.id)}
                  className={`cursor-pointer border-b border-rule transition-colors hover:bg-card ${s.brand.id === selected?.brand.id ? "bg-card" : ""}`}
                >
                  <td className="py-3 font-serif text-[15px]">{s.brand.brand}</td>
                  <td className="py-3"><CountryMark code={s.brand.region} /></td>
                  <td className="py-3 text-right tabular-nums">{s.bids.length}</td>
                  <td className="py-3 text-right tabular-nums">{s.won.length}</td>
                  <td className="py-3 text-right tabular-nums">{s.winRate !== undefined ? pct(s.winRate) : "—"}</td>
                  <td className="py-3 text-right tabular-nums">{s.spend ? cash(s.spend) : "—"}</td>
                  <td className="py-3 text-right tabular-nums">{s.impressions ? compact(s.impressions) : "—"}</td>
                  <td className="py-3 text-right tabular-nums">{s.cpm !== undefined ? `${currency === "USD" ? "$" : "€"}${s.cpm.toFixed(2)}` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
    </>
  );
}

function CompanyDetail({ s }: { s: CompanyStats }) {
  const { slots, results, currency } = useMarket();
  const cash = (n: number) => money(n, currency);
  const history = [...s.bids].sort((a, b) => b.placed_at.localeCompare(a.placed_at));

  return (
    <>
      <div className="mt-12 grid gap-10 md:grid-cols-[minmax(0,1fr)_300px]">
        <div>
          <h2 className="font-serif text-4xl font-medium tracking-tight">{s.brand.brand}</h2>
          <p className="mt-2 flex items-center gap-3 text-sm text-muted">
            {s.brand.category && (
              <>
                <span className="capitalize">{s.brand.category}</span>·
              </>
            )}
            <CountryMark code={s.brand.region} muted />
          </p>
          <div className="mt-8 grid grid-cols-2 gap-x-8 gap-y-8 sm:grid-cols-3">
            <Stat label="Placements won" value={s.won.length} format={num} note={`of ${s.decided} decided`} />
            <Stat label="Win rate" value={s.winRate} format={pct} />
            <Stat label="Total spend" value={s.spend} format={cash} />
            <Stat label="Impressions" value={s.impressions} format={compact} note="simulated" />
            <Stat label="Cost per 1,000 views" value={s.cpm} format={(n) => `${currency === "USD" ? "$" : "€"}${n.toFixed(2)}`} />
            <Stat label="Avg. visibility" value={s.avgVisibility} format={(n) => `${dec(n)} / 10`} />
          </div>
        </div>
        <div>
          <AdCreative ad={s.brand} />
          <p className="mt-2 text-xs text-muted">{s.brand.creative ? "The brand's ad" : "Creative on file"}</p>
        </div>
      </div>

      <Section title="Impressions, first 14 days" aside="Simulated from audience estimates">
        <ImpressionsChart total={s.impressions} seed={s.brand.id} />
      </Section>

      <Section title="Bid history" aside={`${history.length} bid${history.length === 1 ? "" : "s"}`}>
        {history.length === 0 ? (
          <p className="text-sm text-muted">This company has not bid yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm">
              <thead>
                <tr className="border-b border-ink text-left text-xs uppercase tracking-[0.12em] text-muted">
                  <th className="py-2 font-medium">Placement</th>
                  <th className="py-2 font-medium">Market</th>
                  <th className="py-2 text-right font-medium">Bid</th>
                  <th className="py-2 font-medium pl-6">Result</th>
                  <th className="py-2 text-right font-medium">Paid</th>
                </tr>
              </thead>
              <tbody>
                {history.map((b) => {
                  const slot = slots.find((x) => x.id === b.slot_id);
                  const r = results[b.slot_id];
                  const outcome = r?.outcomes.find((o) => o.bid.id === b.id);
                  const label = !r ? "Open" : outcome?.status === "won" ? "Won" : outcome?.status === "rejected" ? `Rejected · ${outcome.reason}` : "Lost";
                  return (
                    <tr key={b.id} className="border-b border-rule">
                      <td className="py-3">{slot?.title ?? b.slot_id}</td>
                      <td className="py-3">{slot && <CountryMark code={slot.region} />}</td>
                      <td className="py-3 text-right tabular-nums">{cash(b.amount)}</td>
                      <td className={`py-3 pl-6 ${label === "Won" ? "text-positive" : label.startsWith("Rejected") ? "text-accent" : "text-muted"}`}>{label}</td>
                      <td className="py-3 text-right tabular-nums">{outcome?.status === "won" && r?.price !== undefined ? cash(r.price) : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </>
  );
}

/** Afișările unei campanii scad pe măsură ce filmul iese din cinematografe; curbă simulată, deterministă per brand. */
function ImpressionsChart({ total, seed }: { total: number; seed: string }) {
  if (!total) return <p className="text-sm text-muted">No placements running yet, so there is nothing to chart.</p>;

  const s = [...seed].reduce((a, c) => a + c.charCodeAt(0), 0);
  const raw = Array.from({ length: 14 }, (_, d) => Math.exp(-d / 5) * (1 + 0.12 * Math.sin(s + d * 1.7)));
  const sum = raw.reduce((a, b) => a + b, 0);
  const values = raw.map((v) => (v / sum) * total);

  const W = 1100, H = 280, L = 56, R = 16, T = 12, B = 30;
  const max = Math.max(...values) * 1.1;
  const x = (i: number) => L + (i / 13) * (W - L - R);
  const y = (v: number) => T + (1 - v / max) * (H - T - B);
  const line = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const area = `${line} L${x(13)},${H - B} L${x(0)},${H - B} Z`;
  const ticks = [0, 0.5, 1].map((f) => f * max);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`Simulated daily impressions, ${compact(total)} in total`}>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="var(--rule)" />
          <text x={L - 8} y={y(t) + 4} textAnchor="end" fontSize="12" fill="var(--muted)">
            {compact(t)}
          </text>
        </g>
      ))}
      {[0, 6, 13].map((i) => (
        <text key={i} x={x(i)} y={H - 8} textAnchor={i === 0 ? "start" : i === 13 ? "end" : "middle"} fontSize="12" fill="var(--muted)">
          Day {i + 1}
        </text>
      ))}
      <motion.path d={area} fill="var(--accent-soft)" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6, delay: 0.3 }} />
      <motion.path
        d={line}
        fill="none"
        stroke="var(--ink)"
        strokeWidth={1.75}
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.9, ease: [0.2, 0.7, 0.2, 1] }}
      />
      {values.map((v, i) => (
        <circle key={i} cx={x(i)} cy={y(v)} r={2.5} fill="var(--card)" stroke="var(--ink)" strokeWidth={1.25}>
          <title>{`Day ${i + 1}: ${num(v)}`}</title>
        </circle>
      ))}
    </svg>
  );
}
