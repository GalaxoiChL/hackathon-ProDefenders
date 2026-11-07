import { NavLink } from "react-router-dom";
import { motion } from "framer-motion";
import type { TabDef } from "../tabs.config";

export function TopBar({ tabs }: { tabs: TabDef[] }) {
  return (
    <header className="sticky top-0 z-20 border-b border-rule bg-paper/95 backdrop-blur-sm">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-10 gap-y-1 px-4 sm:px-6">
        <NavLink to="/" className="flex items-baseline gap-3 py-4">
          <span className="font-serif text-xl font-semibold tracking-tight">ProDefenders</span>
          <span className="hidden text-xs text-muted md:inline">In-content advertising, localised</span>
        </NavLink>
        <nav className="no-scrollbar -mb-px flex min-w-0 flex-1 gap-7 overflow-x-auto">
          {tabs.map((t) => (
            <NavLink
              key={t.id}
              to={`/${t.id}`}
              className={({ isActive }) =>
                `relative shrink-0 py-4 text-sm transition-colors ${t.align === "end" ? "ml-auto font-medium" : ""} ${isActive ? "text-ink" : "text-muted hover:text-ink"}`
              }
            >
              {({ isActive }) => (
                <>
                  {t.label}
                  {isActive && (
                    <motion.span
                      layoutId="nav-underline"
                      className="absolute inset-x-0 bottom-0 h-[2px] bg-ink"
                      transition={{ duration: 0.3, ease: [0.2, 0.7, 0.2, 1] }}
                    />
                  )}
                </>
              )}
            </NavLink>
          ))}
        </nav>
      </div>
    </header>
  );
}
