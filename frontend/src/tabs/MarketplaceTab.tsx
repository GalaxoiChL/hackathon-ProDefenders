// Marketplace: un tabel cu filmele scoase la vânzare. Click pe un film -> locurile de reclamă din el,
// fiecare cu o licitație separată pe țară, unde orice firmă locală își poate face oferta.
import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useSearchParams } from "react-router-dom";
import { useMarket } from "../market";
import { apiAvailable, assetUrl } from "../data/loadClip";
import {
  CATEGORIES,
  fetchBids,
  fetchMovie,
  fetchMovies,
  moviesFromSlots,
  postBid,
  sampleBids,
  type BidForm,
  type BidResult,
  type Movie,
  type Offer,
  type Place,
  type PublicBid,
} from "../data/movies";
import { regionStyle } from "../regions";
import { Button, CountryMark, CountUp, PageHeader, compact, dec, money, num } from "../components/ui";
import { CountryPicker } from "../components/CountryPicker";

const REFRESH_MS = 15_000;

// ---------------- data: backend if running, otherwise the sample market ----------------
interface MovieMarket {
  mode: "api" | "sample" | "loading";
  movies: Movie[];
  /** filmul complet (cu locurile și ofertele pe țări) */
  useMovie: (clip: string) => { movie?: Movie; reload: () => void };
  bidsFor: (offer: Offer) => Promise<PublicBid[]>;
  submit: (offer: Offer, form: BidForm) => Promise<BidResult>;
}

function useMovieMarket(): MovieMarket {
  const market = useMarket();
  const [api, setApi] = useState<boolean | null>(null);
  const [apiMovies, setApiMovies] = useState<Movie[] | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    apiAvailable().then(setApi);
  }, []);
  useEffect(() => {
    if (!api) return;
    let live = true;
    const load = () => fetchMovies().then((m) => live && setApiMovies(m ?? []));
    load();
    const t = window.setInterval(load, REFRESH_MS);
    return () => {
      live = false;
      clearInterval(t);
    };
  }, [api, tick]);

  const sample = useMemo(() => moviesFromSlots(market.slots, market.bids, market.isClosed), [market.slots, market.bids, market.isClosed]);
  const mode: MovieMarket["mode"] = api === null || (api && apiMovies === null) ? "loading" : api && apiMovies!.length ? "api" : "sample";

  const useMovie = (clip: string) => {
    // hook apelat mereu în aceeași ordine din MovieView
    const [movie, setMovie] = useState<Movie | undefined>();
    const [n, setN] = useState(0);
    useEffect(() => {
      if (mode !== "api") return;
      let live = true;
      const load = () => fetchMovie(clip).then((m) => live && setMovie(m));
      load();
      const t = window.setInterval(load, REFRESH_MS);
      return () => {
        live = false;
        clearInterval(t);
      };
    }, [clip, n, mode]); // mode: loading -> api la prima deschidere
    const reload = useCallback(() => {
      setN((x) => x + 1);
      setTick((x) => x + 1);
    }, []);
    return { movie: mode === "api" ? movie : sample.find((m) => m.clip === clip), reload };
  };

  return {
    mode,
    movies: mode === "api" ? apiMovies! : mode === "sample" ? sample : [],
    useMovie,
    bidsFor: (offer) => (mode === "api" ? fetchBids(offer.id) : Promise.resolve(sampleBids(offer.id, market.bids, market.brands))),
    submit: async (offer, form) => {
      if (mode === "api") return postBid(offer.id, form);
      const error = market.placeOpenBid(offer.id, form.company, form.category, form.amount);
      if (error) return { ok: false, error };
      const others = market.bids.filter((b) => b.slot_id === offer.id && !b.brand_id.endsWith(`:${form.company.trim().toLowerCase()}`));
      const higher = others.filter((b) => b.amount > form.amount).length;
      return { ok: true, rank: higher + 1, leading: higher === 0 };
    },
  };
}

// ---------------- tab ----------------
export default function MarketplaceTab() {
  const [params, setParams] = useSearchParams();
  const data = useMovieMarket();
  const clip = params.get("movie");
  const open = (c: string | null) => {
    setParams(c ? { movie: c } : {});
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  return (
    <AnimatePresence mode="wait">
      <motion.div key={clip ?? "table"} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
        {clip ? <MovieView clip={clip} data={data} onBack={() => open(null)} /> : <MoviesTable data={data} onOpen={open} />}
      </motion.div>
    </AnimatePresence>
  );
}

// ---------------- movies table ----------------
const TABLE_COLS = "md:grid-cols-[128px_minmax(0,1fr)_64px_72px_120px_64px_96px_88px_16px]";

function MoviesTable({ data, onOpen }: { data: MovieMarket; onOpen: (clip: string) => void }) {
  const [query, setQuery] = useState("");
  const [country, setCountry] = useState("all");
  const all = data.movies;
  const markets = [...new Set(all.flatMap((m) => m.markets))];
  const list = all.filter(
    (m) =>
      (!query || `${m.title} ${m.subtitle ?? ""}`.toLowerCase().includes(query.toLowerCase())) &&
      (country === "all" || m.markets.includes(country)),
  );
  const places = all.reduce((n, m) => n + m.places.length, 0);
  const bids = all.reduce((n, m) => n + m.bids, 0);

  return (
    <>
      <PageHeader
        eyebrow="For local businesses"
        title="Marketplace"
        lede="Movies with ad places for sale. Pick a movie, choose one of its billboards and the country where you want to be seen, then place your bid. Each place is a separate auction in every country: viewers there see the highest bidder's ad."
        aside={
          <dl className="flex gap-8">
            <Figure label="Movies" value={all.length} />
            <Figure label="Ad places" value={places} />
            <Figure label="Bids placed" value={bids} />
          </dl>
        }
      />
      {data.mode === "sample" && (
        <p className="-mt-6 mb-8 border-l-2 border-accent pl-3 text-sm text-ink-2">
          Sample movies: start the server (backend/) to sell the clips you rendered. Bids placed here stay in this browser.
        </p>
      )}

      <div className="mb-6 flex flex-wrap items-end gap-4">
        <label className="text-sm">
          <span className="mb-1.5 block text-xs uppercase tracking-[0.14em] text-muted">Search</span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Movie or scene"
            className="w-64 border border-rule-strong bg-card px-3 py-2 text-sm text-ink outline-none focus:border-ink"
          />
        </label>
        <div className="text-sm">
          <span className="mb-1.5 block text-xs uppercase tracking-[0.14em] text-muted">Your market</span>
          <CountryPicker
            allLabel="All countries"
            value={country}
            onChange={setCountry}
            options={markets.map((c) => ({ code: c, detail: `${all.filter((m) => m.markets.includes(c)).length} movies` }))}
          />
        </div>
      </div>

      <div role="table" aria-label="Movies for sale">
        <div role="row" className={`hidden items-end gap-4 border-b border-ink pb-2 text-xs uppercase tracking-[0.12em] text-muted md:grid ${TABLE_COLS}`}>
          <span role="columnheader" />
          <span role="columnheader">Movie</span>
          <span role="columnheader">Length</span>
          <span role="columnheader">Places</span>
          <span role="columnheader">Countries</span>
          <span role="columnheader" className="text-right">Bids</span>
          <span role="columnheader" className="text-right">Highest</span>
          <span role="columnheader" className="text-right">From</span>
          <span />
        </div>
        {data.mode === "loading" && <p className="py-10 text-sm text-muted">Loading movies…</p>}
        {data.mode !== "loading" && list.length === 0 && <p className="py-10 text-sm text-muted">No movies match.</p>}
        {list.map((m) => (
          <button
            key={m.clip}
            role="row"
            onClick={() => onOpen(m.clip)}
            className={`group grid w-full grid-cols-[112px_minmax(0,1fr)] items-center gap-4 border-b border-rule py-4 pr-2 text-left transition-colors hover:bg-card ${TABLE_COLS}`}
          >
            <Poster movie={m} />
            <div className="min-w-0" role="cell">
              <p className="font-serif text-lg leading-snug group-hover:underline group-hover:decoration-rule-strong group-hover:underline-offset-4">{m.title}</p>
              {m.subtitle && <p className="mt-0.5 truncate text-xs capitalize text-muted">{m.subtitle}</p>}
              <p className="mt-2 text-xs text-ink-2 md:hidden">
                {m.places.length} ad place{m.places.length === 1 ? "" : "s"} · {m.markets.length} countries · {m.bids} bids
                {m.top_bid !== undefined && <> · top {money(m.top_bid, m.currency)}</>}
              </p>
            </div>
            <span role="cell" className="hidden text-sm tabular-nums md:block">{m.duration_s !== undefined ? `${dec(m.duration_s)} s` : "—"}</span>
            <span role="cell" className="hidden text-sm tabular-nums md:block">{m.places.length}</span>
            <span role="cell" className="hidden md:block"><Flags codes={m.markets} /></span>
            <span role="cell" className="hidden text-right text-sm tabular-nums md:block">{num(m.bids)}</span>
            <span role="cell" className="hidden text-right text-sm font-medium tabular-nums md:block">{m.top_bid !== undefined ? money(m.top_bid, m.currency) : "—"}</span>
            <span role="cell" className="hidden text-right text-sm tabular-nums text-muted md:block">{m.min_floor !== undefined ? money(m.min_floor, m.currency) : "—"}</span>
            <span aria-hidden className="hidden text-muted transition-transform group-hover:translate-x-0.5 md:block">→</span>
          </button>
        ))}
      </div>
    </>
  );
}

function Figure({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-1 font-serif text-2xl tabular-nums">
        <CountUp value={value} format={num} />
      </dd>
    </div>
  );
}

function Poster({ movie, large = false }: { movie: Movie; large?: boolean }) {
  const [broken, setBroken] = useState(false);
  return (
    <div className={`relative aspect-video overflow-hidden bg-screen ${large ? "w-full" : "w-[112px] md:w-[128px]"}`}>
      {movie.thumbnail_url && !broken ? (
        <img src={assetUrl(movie.thumbnail_url)} alt="" onError={() => setBroken(true)} className="h-full w-full object-cover" />
      ) : (
        <span className="absolute inset-0 grid place-items-center font-serif text-sm text-[#d9d5cc]">{movie.title}</span>
      )}
      <span className="absolute bottom-1 right-1 bg-black/70 px-1.5 py-0.5 text-[10px] font-medium text-white">
        {movie.places.length} place{movie.places.length === 1 ? "" : "s"}
      </span>
    </div>
  );
}

/** Steaguri colorate (culoarea țării), primele 5 + câte mai sunt. */
function Flags({ codes }: { codes: string[] }) {
  const shown = codes.slice(0, 5);
  return (
    <span className="inline-flex items-center gap-1" title={codes.map((c) => regionStyle(c).name).join(", ")}>
      {shown.map((c) => (
        <span key={c} className="grid h-5 w-6 place-items-center text-[9px] font-semibold text-white" style={{ background: regionStyle(c).color }}>
          {c}
        </span>
      ))}
      {codes.length > shown.length && <span className="pl-0.5 text-xs text-muted">+{codes.length - shown.length}</span>}
    </span>
  );
}

// ---------------- one movie: its ad places, one auction per country ----------------
function MovieView({ clip, data, onBack }: { clip: string; data: MovieMarket; onBack: () => void }) {
  const { movie, reload } = data.useMovie(clip);
  const [country, setCountry] = useState("all");
  const [openOffer, setOpenOffer] = useState<string | null>(null);

  if (!movie) {
    return (
      <div>
        <BackLink onClick={onBack} />
        <p className="py-16 text-sm text-muted">{data.mode === "loading" || data.mode === "api" ? "Loading the movie…" : `No movie called “${clip}”.`}</p>
      </div>
    );
  }

  return (
    <div>
      <BackLink onClick={onBack} />
      <header className="mb-8 mt-4 grid gap-8 border-b border-rule pb-8 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-accent">Movie</p>
          <h1 className="mt-3 font-serif text-4xl font-medium tracking-tight sm:text-5xl">{movie.title}</h1>
          <p className="mt-3 text-[15px] text-ink-2">
            {movie.subtitle && <span className="capitalize">{movie.subtitle}</span>}
            {movie.subtitle && movie.duration_s !== undefined && " · "}
            {movie.duration_s !== undefined && `${dec(movie.duration_s)} s`}
          </p>
          <div className="mt-6">
            {movie.video_url ? (
              <video
                key={movie.video_url}
                src={assetUrl(movie.video_url)}
                poster={movie.thumbnail_url ? assetUrl(movie.thumbnail_url) : undefined}
                controls
                muted
                playsInline
                preload="metadata"
                className="aspect-video w-full bg-screen"
              />
            ) : (
              <Poster movie={movie} large />
            )}
          </div>
        </div>
        <aside className="self-end">
          <dl className="grid grid-cols-2 gap-x-6 gap-y-5">
            <Fact label="Ad places" value={movie.places.length} />
            <Fact label="Countries" value={movie.markets.length} />
            <Fact label="Bids so far" value={num(movie.bids)} />
            <Fact label="Highest bid" value={movie.top_bid !== undefined ? money(movie.top_bid, movie.currency) : "—"} />
          </dl>
          <p className="mt-6 text-sm leading-relaxed text-ink-2">
            Every ad place is sold separately in every country. Viewers in a country see the ad of the business that wins that country's
            auction; the rest of the world sees someone else.
          </p>
          <div className="mt-5 text-sm">
            <span className="mb-1.5 block text-xs uppercase tracking-[0.14em] text-muted">Show country</span>
            <CountryPicker
              allLabel="All countries"
              value={country}
              onChange={(c) => {
                setCountry(c);
                setOpenOffer(null);
              }}
              options={movie.markets.map((c) => ({ code: c }))}
            />
          </div>
        </aside>
      </header>

      {movie.places.map((p) => (
        <PlaceSection
          key={p.id}
          place={p}
          movie={movie}
          country={country}
          openOffer={openOffer}
          onToggle={(id) => setOpenOffer((cur) => (cur === id ? null : id))}
          data={data}
          onBid={reload}
        />
      ))}
    </div>
  );
}

function BackLink({ onClick }: { onClick: () => void }) {
  return (
    <button onClick={onClick} className="text-sm text-ink-2 underline decoration-rule-strong underline-offset-4 hover:decoration-ink">
      ← All movies
    </button>
  );
}

function Fact({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="border-t border-ink pt-2">
      <dt className="text-xs uppercase tracking-[0.12em] text-muted">{label}</dt>
      <dd className="mt-1 font-serif text-2xl tabular-nums">{value}</dd>
    </div>
  );
}

const OFFER_COLS = "grid-cols-[minmax(0,1fr)_88px_auto] sm:grid-cols-[minmax(0,1fr)_96px_56px_104px_88px]";

function PlaceSection({
  place,
  movie,
  country,
  openOffer,
  onToggle,
  data,
  onBid,
}: {
  place: Place;
  movie: Movie;
  country: string;
  openOffer: string | null;
  onToggle: (id: string) => void;
  data: MovieMarket;
  onBid: () => void;
}) {
  const offers = place.offers.filter((o) => country === "all" || o.market === country);
  const [broken, setBroken] = useState(false);
  return (
    <section className="mb-14">
      <div className="mb-5 flex flex-wrap items-baseline justify-between gap-3 border-b border-rule pb-3">
        <h2 className="font-serif text-2xl font-medium tracking-tight">
          {place.label}
          {place.type && <span className="ml-2 text-base capitalize text-muted">· {place.type}</span>}
        </h2>
        <p className="text-sm text-muted">
          {[
            place.frame_share_pct !== undefined ? `${dec(place.frame_share_pct)}% of the frame` : undefined,
            place.confidence !== undefined ? `found by AI with ${Math.round(place.confidence * 100)}% confidence` : undefined,
            `${place.bids} bid${place.bids === 1 ? "" : "s"}`,
          ]
            .filter(Boolean)
            .join(" · ")}
        </p>
      </div>

      <div className="grid gap-8 lg:grid-cols-[280px_minmax(0,1fr)]">
        <figure className="self-start">
          <div className="relative aspect-[4/3] overflow-hidden bg-screen">
            {place.image_url && !broken ? (
              <img src={assetUrl(place.image_url)} alt={`${place.label} in ${movie.title}`} onError={() => setBroken(true)} className="h-full w-full object-cover" />
            ) : (
              <span className="absolute inset-0 grid place-items-center px-4 text-center font-serif text-sm text-[#d9d5cc]">
                {place.label}
                <br />
                {movie.title}
              </span>
            )}
          </div>
          <figcaption className="mt-2 text-xs leading-relaxed text-muted">
            Outlined: where your ad goes. It follows the camera and stays behind people walking past.
          </figcaption>
        </figure>

        <div role="table" aria-label={`${place.label}: one auction per country`}>
          <div role="row" className={`grid gap-3 border-b border-ink pb-2 text-xs uppercase tracking-[0.12em] text-muted ${OFFER_COLS}`}>
            <span role="columnheader">Country</span>
            <span role="columnheader" className="hidden text-right sm:block">Minimum</span>
            <span role="columnheader" className="hidden text-right sm:block">Bids</span>
            <span role="columnheader" className="text-right">Highest</span>
            <span />
          </div>
          {offers.map((o) => (
            <OfferRow key={o.id} offer={o} open={openOffer === o.id} onToggle={() => onToggle(o.id)} data={data} onBid={onBid} />
          ))}
        </div>
      </div>
    </section>
  );
}

function OfferRow({ offer, open, onToggle, data, onBid }: { offer: Offer; open: boolean; onToggle: () => void; data: MovieMarket; onBid: () => void }) {
  const closed = offer.status === "closed";
  return (
    <div role="rowgroup" className={`border-b border-rule ${open ? "bg-card" : ""}`}>
      <div role="row" className={`grid items-center gap-3 py-3 ${OFFER_COLS} ${open ? "px-3" : ""} transition-[padding]`}>
        <span role="cell">
          <CountryMark code={offer.market} />
        </span>
        <span role="cell" className="hidden text-right text-sm tabular-nums text-muted sm:block">{money(offer.floor, offer.currency)}</span>
        <span role="cell" className="hidden text-right text-sm tabular-nums sm:block">{offer.bids}</span>
        <span role="cell" className="text-right text-sm font-medium tabular-nums">{offer.top_bid !== undefined ? money(offer.top_bid, offer.currency) : "—"}</span>
        <span role="cell" className="text-right">
          {closed ? (
            <span className="text-sm text-muted">Closed</span>
          ) : (
            <Button variant={open ? "secondary" : "primary"} className="!px-4 !py-1.5" onClick={onToggle}>
              {open ? "Close" : "Bid"}
            </Button>
          )}
        </span>
      </div>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.22 }} className="overflow-hidden">
            <div className="grid gap-8 px-3 pb-6 pt-2 md:grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)]">
              <BidPanel offer={offer} data={data} onBid={onBid} />
              <BidsList offer={offer} data={data} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

const field = "mt-1 block w-full border border-rule-strong bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-ink";

function BidPanel({ offer, data, onBid }: { offer: Offer; data: MovieMarket; onBid: () => void }) {
  const [form, setForm] = useState<BidForm>({ company: "", email: "", category: offer.categories?.[0] ?? "food", amount: Math.ceil(offer.floor), message: "" });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const set = <K extends keyof BidForm>(k: K, v: BidForm[K]) => setForm((f) => ({ ...f, [k]: v }));
  const symbol = offer.currency === "USD" ? "$" : "€";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    const r = await data.submit(offer, form);
    setBusy(false);
    if (!r.ok) return setMsg({ ok: false, text: r.error });
    setMsg({ ok: true, text: r.leading ? "Bid placed. You are the highest bidder for this place in this country." : `Bid placed. You are #${r.rank}; raise it to lead.` });
    onBid();
  };

  return (
    <form onSubmit={submit}>
      <p className="font-serif text-lg">
        Bid for {regionStyle(offer.market).name}
      </p>
      <p className="mt-1 text-xs text-muted">
        Minimum {money(offer.floor, offer.currency)} · about {compact(offer.expected_views)} viewers · {money(offer.cpm, offer.currency)} CPM
      </p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <label className="block text-xs text-muted">
          Company
          <input required minLength={2} value={form.company} onChange={(e) => set("company", e.target.value)} placeholder="Your business name" className={field} />
        </label>
        <label className="block text-xs text-muted">
          Contact email
          <input
            required
            type="email"
            value={form.email}
            onChange={(e) => set("email", e.target.value)}
            placeholder="you@business.com"
            className={field}
          />
        </label>
        <label className="block text-xs text-muted">
          Category
          <select value={form.category} onChange={(e) => set("category", e.target.value)} className={`${field} capitalize`}>
            {[...new Set([...(offer.categories ?? []), ...CATEGORIES])].map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-xs text-muted">
          Your bid
          <span className="mt-1 flex items-center border border-rule-strong bg-paper focus-within:border-ink">
            <span className="pl-3 text-sm text-muted">{symbol}</span>
            <input
              required
              type="number"
              inputMode="numeric"
              min={Math.ceil(offer.floor)}
              step={1}
              value={Number.isFinite(form.amount) ? form.amount : ""}
              onChange={(e) => set("amount", Number(e.target.value))}
              className="w-full bg-transparent px-2 py-2 text-sm tabular-nums text-ink outline-none"
            />
          </span>
        </label>
      </div>
      <label className="mt-3 block text-xs text-muted">
        Message (optional)
        <textarea rows={2} value={form.message} onChange={(e) => set("message", e.target.value)} placeholder="What you would like to show" className={field} />
      </label>
      <Button type="submit" className="mt-4 w-full sm:w-auto" disabled={busy}>
        {busy ? "Placing…" : `Place bid · ${symbol}${num(form.amount || 0)}`}
      </Button>
      <p className="mt-2 text-xs text-muted">Your email is only shared with the movie owner. Bidding again replaces your previous bid.</p>
      <AnimatePresence>
        {msg && (
          <motion.p key={msg.text} role="status" initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className={`mt-3 text-sm ${msg.ok ? "text-positive" : "text-accent"}`}>
            {msg.text}
          </motion.p>
        )}
      </AnimatePresence>
    </form>
  );
}

/** Backend-ul salvează categoria în fața mesajului: "[food] text". */
function BidNote({ message }: { message?: string }) {
  if (!message) return null;
  const m = /^\[([^\]]+)\]\s*(.*)$/s.exec(message);
  const [category, text] = m ? [m[1], m[2]] : [undefined, message];
  return (
    <span className="mt-0.5 flex min-w-0 items-center gap-2 text-xs text-muted">
      {category && <span className="shrink-0 border border-rule-strong px-1.5 capitalize">{category}</span>}
      {text && <span className="truncate">{text}</span>}
    </span>
  );
}

function BidsList({ offer, data }: { offer: Offer; data: MovieMarket }) {
  const [bids, setBids] = useState<PublicBid[] | null>(null);
  useEffect(() => {
    let live = true;
    const load = () => data.bidsFor(offer).then((b) => live && setBids(b));
    load();
    const t = window.setInterval(load, REFRESH_MS);
    return () => {
      live = false;
      clearInterval(t);
    };
    // offer.bids / top_bid change after every new bid: reload the list then
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offer.id, offer.bids, offer.top_bid]);

  return (
    <div>
      <p className="text-xs uppercase tracking-[0.14em] text-muted">Bids for this place in {regionStyle(offer.market).name} · {bids?.length ?? "…"}</p>
      {bids && bids.length === 0 && <p className="mt-3 text-sm text-ink-2">No bids yet. The first one at or above the minimum leads.</p>}
      <ol className="mt-2">
        <AnimatePresence initial={false}>
          {bids?.map((b, i) => (
            <motion.li
              key={b.id}
              layout
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              className="grid grid-cols-[20px_minmax(0,1fr)_auto] items-baseline gap-2 border-b border-rule py-2 text-sm"
            >
              <span className="text-xs tabular-nums text-muted">{i + 1}</span>
              <span className="min-w-0">
                <span className={i === 0 ? "font-medium" : ""}>{b.company}</span>
                <BidNote message={b.message} />
              </span>
              <span className="text-right tabular-nums">
                {money(b.amount, offer.currency)}
                <span className="block text-[11px] text-muted">
                  {new Date(b.placed_at).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                </span>
              </span>
            </motion.li>
          ))}
        </AnimatePresence>
      </ol>
    </div>
  );
}
