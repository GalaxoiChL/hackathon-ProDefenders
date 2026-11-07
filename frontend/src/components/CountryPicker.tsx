// Un singur buton care arată țara aleasă și deschide lista tuturor țărilor (până la 15 piețe).
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, ChevronDown } from "lucide-react";
import { regionName, regionStyle } from "../regions";

export interface CountryOption {
  code: string;
  label?: string;
  /** text mic sub nume, ex. brandul de pe panou */
  detail?: string;
}

export function CountryPicker({ options, value, onChange }: { options: CountryOption[]; value: string; onChange: (code: string) => void }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const current = options.find((o) => o.code === value) ?? options[0];

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => !root.current?.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!current) return null;
  return (
    <div ref={root} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="flex min-w-56 items-center gap-3 border border-rule-strong bg-card px-3 py-2 text-left text-sm outline-none transition-colors hover:border-ink focus-visible:border-ink"
      >
        <span className="h-4 w-1 shrink-0" style={{ background: regionStyle(current.code).color }} />
        <span className="flex-1">{regionName(current.code, current.label)}</span>
        <motion.span animate={{ rotate: open ? 180 : 0 }} transition={{ duration: 0.2 }} className="text-muted">
          <ChevronDown size={16} />
        </motion.span>
      </button>

      <AnimatePresence>
        {open && (
          <motion.ul
            role="listbox"
            aria-label="Country"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.16 }}
            className="absolute right-0 z-30 mt-1 max-h-80 w-72 overflow-y-auto border border-rule-strong bg-card py-1 shadow-lg"
          >
            {options.map((o) => {
              const selected = o.code === current.code;
              return (
                <li key={o.code} role="option" aria-selected={selected}>
                  <button
                    onClick={() => {
                      onChange(o.code);
                      setOpen(false);
                    }}
                    className={`flex w-full items-center gap-3 px-3 py-2 text-left text-sm transition-colors hover:bg-paper ${selected ? "bg-paper" : ""}`}
                  >
                    <span className="h-4 w-1 shrink-0" style={{ background: regionStyle(o.code).color }} />
                    <span className="min-w-0 flex-1">
                      <span className="block">{regionName(o.code, o.label)}</span>
                      {o.detail && <span className="block truncate text-xs text-muted">{o.detail}</span>}
                    </span>
                    {selected && <Check size={15} className="shrink-0" />}
                  </button>
                </li>
              );
            })}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
}
