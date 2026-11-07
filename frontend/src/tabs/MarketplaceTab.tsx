import { useState, type FormEvent, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useMarket } from "../market";
import { reservePrice } from "../data/auction";
import { regionStyle } from "../regions";
import type { Slot } from "../data/types";
import { Button, CountryMark, CountUp, PageHeader, Segmented, compact, dec, eur, num, useNow } from "../components/ui";

type StatusFilter = "all" | "open" | "closed";

export default function MarketplaceTab() {
  const { slots, bids, isClosed, results } = useMarket();
  const [country, setCountry] = useState("all");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const countries = [...new Set(slots.map((s) => s.region))];
  const list = slots.filter(
    (s) => (country === "all" || s.region === country) && (status === "all" || (status === "closed") === isClosed(s.id)),
  );
  const selected = list.find((s) => s.id === selectedId) ?? list[0];
  const openCount = slots.filter((s) => !isClosed(s.id)).length;
  const sold = Object.values(results).reduce((sum, r) => sum + (r.price ?? 0), 0);

  return (
    <>
      <PageHeader
        eyebrow="For brands"
        title="Marketplace"
        lede="Brands bid on billboards inside approved scenes, market by market. Bids are sealed; when the auction closes, the highest eligible bid wins and pays the second-highest price."
        aside={
          <dl className="flex gap-8">
            <Figure label="Open auctions" value={openCount} format={num} />
            <Figure label="Bids placed" value={bids.length} format={num} />
            <Figure label="Sold to date" value={sold} format={eur} />
          </dl>
        }
      />

      <div className="mb-6 flex flex-wrap items-center gap-3">
        <Segmented
          id="mk-country"
          label="Country"
          value={country}
          onChange={setCountry}
          options={[{ value: "all", label: "All markets" }, ...countries.map((c) => ({ value: c, label: regionStyle(c).name }))]}
        />
        <Segmented
          id="mk-status"
          label="Status"
          value={status}
          onChange={setStatus}
          options={[
            { value: "all", label: "All" },
            { value: "open", label: "Open" },
            { value: "closed", label: "Closed" },
          ]}
        />
      </div>

      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div>
          <div className={`hidden gap-4 border-b border-ink pb-2 text-xs uppercase tracking-[0.12em] text-muted md:grid ${ROW_COLS}`}>
            <span />
            <span>Placement</span>
            <span>Market</span>
            <span className="text-right">Minimum</span>
            <span>Status</span>
          </div>
          {list.length === 0 && <p className="py-10 text-sm text-muted">No placements match these filters.</p>}
          {list.map((s) => (
            <SlotRow key={s.id} slot={s} active={s.id === selected?.id} onSelect={() => setSelectedId(s.id)} />
          ))}
        </div>

        <aside className="self-start lg:sticky lg:top-24">
          <AnimatePresence mode="wait">
            {selected && (
              <motion.div key={selected.id} initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
                <SlotDetail slot={selected} />
              </motion.div>
            )}
          </AnimatePresence>
        </aside>
      </div>
    </>
  );
}

function Figure({ label, value, format }: { label: string; value: number; format: (n: number) => string }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-1 font-serif text-2xl tabular-nums">
        <CountUp value={value} format={format} />
      </dd>
    </div>
  );
}

function Thumb({ slot, large = false }: { slot: Slot; large?: boolean }) {
  return (
    <div className={`relative aspect-video overflow-hidden bg-screen ${large ? "w-full" : "w-[72px]"}`}>
      {slot.thumbnail ? (
        <img src={slot.thumbnail} alt="" className="h-full w-full object-cover" />
      ) : (
        <span className={`absolute inset-0 grid place-items-center font-serif capitalize text-[#d9d5cc] ${large ? "text-2xl" : "text-[11px]"}`}>{slot.clip}</span>
      )}
      <span className="absolute inset-x-0 bottom-0 h-[3px]" style={{ background: regionStyle(slot.region).color }} />
    </div>
  );
}

function StatusLabel({ slot }: { slot: Slot }) {
  const { isClosed, results, deadlines } = useMarket();
  const now = useNow();
  if (!isClosed(slot.id)) {
    const left = Math.max(0, (deadlines[slot.id] ?? now) - now) / 1000;
    return (
      <span className="inline-flex items-center gap-2 text-sm">
        <span className="size-1.5 animate-pulse rounded-full bg-positive" />
        <span className="tabular-nums">
          {Math.floor(left / 60)}:{String(Math.floor(left % 60)).padStart(2, "0")} left
        </span>
      </span>
    );
  }
  const r = results[slot.id];
  return r?.price !== undefined ? <span className="text-sm">Sold · {eur(r.price)}</span> : <span className="text-sm text-muted">Unsold</span>;
}

const ROW_COLS = "md:grid-cols-[72px_minmax(0,1fr)_112px_84px_112px]";

function SlotRow({ slot, active, onSelect }: { slot: Slot; active: boolean; onSelect: () => void }) {
  return (
    <button
      onClick={onSelect}
      className={`relative grid w-full grid-cols-[72px_minmax(0,1fr)] items-center gap-4 border-b border-rule py-4 pr-2 text-left transition-colors ${ROW_COLS} ${
        active ? "bg-card" : "hover:bg-card/60"
      }`}
    >
      {active && <motion.span layoutId="slot-active" className="absolute inset-y-0 -left-3 w-[2px] bg-ink" />}
      <Thumb slot={slot} />
      <div className="min-w-0">
        <p className="font-serif text-base leading-snug">{slot.title}</p>
        <p className="mt-0.5 text-xs text-muted">
          {dec(slot.screen_time_sec)} s on screen · <span className="capitalize">{slot.categories?.join(", ")}</span>
        </p>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 md:hidden">
          <CountryMark code={slot.region} />
          <StatusLabel slot={slot} />
        </div>
      </div>
      <span className="hidden md:block">
        <CountryMark code={slot.region} />
      </span>
      <span className="hidden text-right text-sm tabular-nums md:block">{eur(reservePrice(slot))}</span>
      <span className="hidden md:block">
        <StatusLabel slot={slot} />
      </span>
    </button>
  );
}

function SlotDetail({ slot }: { slot: Slot }) {
  const { isClosed, closeAuction } = useMarket();
  const closed = isClosed(slot.id);
  return (
    <div>
      <p className="text-xs uppercase tracking-[0.14em] text-accent">Placement</p>
      <h3 className="mt-2 font-serif text-2xl leading-tight">{slot.title}</h3>
      <p className="mt-1 text-sm text-muted capitalize">
        {slot.clip} · surface {slot.surface_id}
      </p>
      <div className="mt-5">
        <Thumb slot={slot} large />
      </div>
      <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-4 text-sm">
        <Fact label="Market" value={<CountryMark code={slot.region} />} />
        <Fact label="On screen" value={`${dec(slot.screen_time_sec)} s`} />
        <Fact label="Visibility" value={`${dec(slot.visibility)} / 10`} />
        <Fact label="Audience" value={compact(slot.audience)} />
        <Fact label="CPM" value={eur(slot.cpm_eur)} />
        <Fact label="Minimum price" value={<b>{eur(reservePrice(slot))}</b>} />
      </dl>
      <p className="mt-3 text-xs leading-relaxed text-muted">
        Minimum = audience ÷ 1,000 × CPM × exposure × visibility. Accepts <span className="capitalize">{slot.categories?.join(", ")}</span>.
      </p>

      <div className="mt-6 border-t border-ink pt-5">
        {closed ? (
          <Result slot={slot} />
        ) : (
          <>
            <BidForm slot={slot} />
            <BidsReceived slot={slot} />
            <Button variant="link" className="mt-5 text-muted" onClick={() => closeAuction(slot.id)}>
              End this auction now (demo)
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-0.5 tabular-nums">{value}</dd>
    </div>
  );
}

function BidForm({ slot }: { slot: Slot }) {
  const { brands, placeBid } = useMarket();
  const local = brands.filter((b) => b.region === slot.region);
  const [brandId, setBrandId] = useState(local[0]?.id ?? "");
  const [amount, setAmount] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const error = placeBid(slot.id, brandId, Number(amount));
    setMsg(error ? { ok: false, text: error } : { ok: true, text: "Sealed bid placed. Amounts stay hidden until the auction closes." });
    if (!error) setAmount("");
  };

  return (
    <form onSubmit={submit}>
      <p className="font-serif text-lg">Place a bid</p>
      <label className="mt-3 block text-xs text-muted">
        Company
        <select value={brandId} onChange={(e) => setBrandId(e.target.value)} className="mt-1 block w-full border border-rule-strong bg-card px-3 py-2 text-sm text-ink outline-none focus:border-ink">
          {local.map((b) => (
            <option key={b.id} value={b.id}>
              {b.brand} ({b.category})
            </option>
          ))}
        </select>
      </label>
      <label className="mt-3 block text-xs text-muted">
        Your bid
        <span className="mt-1 flex items-center border border-rule-strong bg-card focus-within:border-ink">
          <span className="pl-3 text-sm text-muted">€</span>
          <input
            type="number"
            inputMode="numeric"
            min={0}
            step={100}
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder={num(reservePrice(slot))}
            className="w-full bg-transparent px-2 py-2 text-sm text-ink tabular-nums outline-none"
          />
        </span>
      </label>
      <Button type="submit" className="mt-4 w-full" disabled={!brandId}>
        Place sealed bid
      </Button>
      <AnimatePresence>
        {msg && (
          <motion.p
            key={msg.text}
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className={`mt-3 text-sm ${msg.ok ? "text-positive" : "text-accent"}`}
          >
            {msg.text}
          </motion.p>
        )}
      </AnimatePresence>
    </form>
  );
}

function BidsReceived({ slot }: { slot: Slot }) {
  const { bids, brands } = useMarket();
  const list = bids.filter((b) => b.slot_id === slot.id).sort((a, b) => b.placed_at.localeCompare(a.placed_at));
  return (
    <div className="mt-8">
      <p className="text-xs uppercase tracking-[0.14em] text-muted">Bids received · {list.length}</p>
      <ul className="mt-2">
        <AnimatePresence initial={false}>
          {list.map((b) => (
            <motion.li
              key={b.id}
              layout
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25 }}
              className="flex items-baseline justify-between border-b border-rule py-2 text-sm"
            >
              <span>{brands.find((x) => x.id === b.brand_id)?.brand ?? b.brand_id}</span>
              <span className="font-mono text-xs text-muted">sealed · {new Date(b.placed_at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}</span>
            </motion.li>
          ))}
        </AnimatePresence>
      </ul>
    </div>
  );
}

const OUTCOME = {
  won: { label: "Won", cls: "text-positive" },
  lost: { label: "Lost", cls: "text-muted" },
  rejected: { label: "Rejected", cls: "text-accent" },
} as const;

function Result({ slot }: { slot: Slot }) {
  const { results, brands } = useMarket();
  const r = results[slot.id];
  const name = (id: string) => brands.find((b) => b.id === id)?.brand ?? id;
  if (!r) return null;
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>
      {r.winner && r.price !== undefined ? (
        <>
          <p className="text-xs uppercase tracking-[0.14em] text-muted">Sold to</p>
          <p className="mt-1 font-serif text-3xl">{name(r.winner.brand_id)}</p>
          <p className="mt-2 text-sm">
            Pays <b className="tabular-nums">{eur(r.price)}</b> <span className="text-muted">· bid {eur(r.winner.amount_eur)}</span>
          </p>
          <p className="mt-2 text-xs leading-relaxed text-muted">Second-price rule: the winner pays the next-highest eligible bid, never less than the minimum price.</p>
        </>
      ) : (
        <p className="text-sm text-ink-2">No eligible bids. The placement stays unsold and viewers see the original scene.</p>
      )}
      <ul className="mt-6">
        {r.outcomes.map((o) => (
          <li key={o.bid.id} className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 border-b border-rule py-2.5 text-sm">
            <span>{name(o.bid.brand_id)}</span>
            <span className="tabular-nums">{eur(o.bid.amount_eur)}</span>
            <span className={`text-xs ${OUTCOME[o.status].cls}`}>
              {OUTCOME[o.status].label}
              {o.reason && o.status !== "won" ? ` · ${o.reason}` : ""}
            </span>
          </li>
        ))}
      </ul>
    </motion.div>
  );
}
