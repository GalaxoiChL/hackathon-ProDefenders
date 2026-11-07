// Componente mici, reutilizabile. Taburile doar le combină.
import { useEffect, useRef, useState, type ReactNode } from "react";
import { animate, motion, useReducedMotion } from "framer-motion";
import { regionStyle } from "../regions";
import type { Ad } from "../data/types";

export function PageHeader({ eyebrow, title, lede, aside }: { eyebrow: string; title: string; lede: string; aside?: ReactNode }) {
  return (
    <header className="mb-10 flex flex-wrap items-end justify-between gap-6 border-b border-rule pb-8">
      <div className="max-w-2xl">
        <p className="text-xs font-medium uppercase tracking-[0.18em] text-accent">{eyebrow}</p>
        <h1 className="mt-3 font-serif text-4xl font-medium tracking-tight sm:text-5xl">{title}</h1>
        <p className="mt-4 text-[15px] leading-relaxed text-ink-2">{lede}</p>
      </div>
      {aside}
    </header>
  );
}

export function Section({ title, aside, children, className = "" }: { title: string; aside?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`mt-14 ${className}`}>
      <div className="mb-5 flex flex-wrap items-baseline justify-between gap-3 border-b border-rule pb-3">
        <h2 className="font-serif text-2xl font-medium tracking-tight">{title}</h2>
        {aside && <div className="text-sm text-muted">{aside}</div>}
      </div>
      {children}
    </section>
  );
}

export function CountryMark({ code, label, muted = false }: { code: string; label?: string; muted?: boolean }) {
  const { color, name } = regionStyle(code, label);
  return (
    <span className={`inline-flex items-center gap-2 text-sm ${muted ? "text-muted" : ""}`}>
      <span className="h-3 w-1 shrink-0" style={{ background: color }} />
      <span>{name}</span>
    </span>
  );
}

/** Butoane de selecție cu un fundal care alunecă sub opțiunea activă. */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  id,
  label,
}: {
  options: { value: T; label: ReactNode }[];
  value: T;
  onChange: (v: T) => void;
  id: string;
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="no-scrollbar inline-flex max-w-full overflow-x-auto border border-rule-strong bg-card p-0.5">
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            role="radio"
            aria-checked={active}
            onClick={() => onChange(o.value)}
            className={`relative shrink-0 px-3.5 py-1.5 text-sm transition-colors ${active ? "text-paper" : "text-ink-2 hover:text-ink"}`}
          >
            {active && <motion.span layoutId={`seg-${id}`} className="absolute inset-0 bg-ink" transition={{ duration: 0.25, ease: [0.2, 0.7, 0.2, 1] }} />}
            <span className="relative">{o.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export function Button({
  children,
  onClick,
  variant = "primary",
  type = "button",
  disabled,
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "link";
  type?: "button" | "submit";
  disabled?: boolean;
  className?: string;
}) {
  const styles = {
    primary: "bg-ink text-paper hover:bg-ink-2 px-5 py-2.5",
    secondary: "border border-rule-strong bg-card hover:border-ink px-4 py-2",
    link: "underline underline-offset-4 decoration-rule-strong hover:decoration-ink",
  };
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={`text-sm font-medium transition-colors disabled:opacity-40 ${styles[variant]} ${className}`}>
      {children}
    </button>
  );
}

/** Număr care urcă până la valoarea finală când apare (oprit dacă utilizatorul a cerut mișcare redusă). */
export function CountUp({ value, format }: { value: number; format: (n: number) => string }) {
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(reduce ? value : 0);
  const from = useRef(reduce ? value : 0);
  useEffect(() => {
    if (reduce) {
      setShown(value);
      return;
    }
    const controls = animate(from.current, value, {
      duration: 0.9,
      ease: [0.2, 0.7, 0.2, 1],
      onUpdate: (v) => {
        from.current = v;
        setShown(v);
      },
    });
    return () => controls.stop();
  }, [value, reduce]);
  return <>{format(shown)}</>;
}

export function Stat({ label, value, format, note }: { label: string; value: number | undefined; format: (n: number) => string; note?: string }) {
  return (
    <div className="border-t border-ink pt-3">
      <p className="text-xs uppercase tracking-[0.14em] text-muted">{label}</p>
      <p className="mt-2 font-serif text-3xl font-medium tabular-nums tracking-tight">
        {value === undefined || Number.isNaN(value) ? "—" : <CountUp value={value} format={format} />}
      </p>
      {note && <p className="mt-1 text-xs text-muted">{note}</p>}
    </div>
  );
}

/** Reclama, așa cum apare pe panou: culorile, titlul și prețul brandului. */
export function AdCreative({ ad, size = "md" }: { ad: Ad; size?: "sm" | "md" }) {
  const c = ad.colors ?? { bg: "#1b1a17", fg: "#ffffff", accent: "#8a1c1c" };
  return (
    <div className="flex flex-col justify-between overflow-hidden" style={{ background: c.bg, color: c.fg, aspectRatio: size === "sm" ? "3 / 2" : "2 / 1" }}>
      <div className={size === "sm" ? "p-3" : "p-5"}>
        <p className={`font-bold tracking-tight ${size === "sm" ? "text-base" : "text-2xl"}`}>{ad.brand}</p>
        <p className={`mt-1 opacity-90 ${size === "sm" ? "text-xs" : "text-sm"}`}>{ad.headline}</p>
      </div>
      <div className={`flex items-center justify-between font-semibold ${size === "sm" ? "px-3 py-1.5 text-xs" : "px-5 py-2 text-sm"}`} style={{ background: c.accent, color: c.bg }}>
        <span className="capitalize">{ad.category}</span>
        <span>{ad.price}</span>
      </div>
    </div>
  );
}

export function Toggle({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className="flex shrink-0 items-center gap-2.5 text-sm text-ink-2 hover:text-ink disabled:opacity-40"
    >
      <span className={`relative h-5 w-9 rounded-full transition-colors duration-200 ${checked ? "bg-ink" : "bg-rule-strong"}`}>
        <motion.span
          className="absolute top-0.5 size-4 rounded-full bg-card shadow-sm"
          animate={{ left: checked ? 18 : 2 }}
          transition={{ duration: 0.2, ease: [0.2, 0.7, 0.2, 1] }}
        />
      </span>
      {label}
    </button>
  );
}

/** Ora curentă, actualizată periodic (pentru numărători inverse). */
export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);
  return now;
}

export const eur =(n: number) => `€${Math.round(n).toLocaleString("en-GB")}`;
export const num = (n: number) => Math.round(n).toLocaleString("en-GB");
export const compact = (n: number) => new Intl.NumberFormat("en-GB", { notation: "compact", maximumFractionDigits: 1 }).format(n);
export const pct = (n: number) => `${Math.round(n * 100)}%`;
export const dec = (n: number) => n.toLocaleString("en-GB", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
