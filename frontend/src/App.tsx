import { useEffect } from "react";
import { HashRouter, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { AnimatePresence, MotionConfig, motion } from "framer-motion";
import { AppProvider, useApp } from "./state";
import { MarketProvider } from "./market";
import { visibleTabs, type TabDef } from "./tabs.config";
import { TopBar } from "./components/TopBar";

export default function App() {
  return (
    <MotionConfig reducedMotion="user">
      <AppProvider>
        <MarketProvider>
          <HashRouter>
            <Shell />
          </HashRouter>
        </MarketProvider>
      </AppProvider>
    </MotionConfig>
  );
}

function Shell() {
  const { data } = useApp();
  const tabs = visibleTabs();
  const location = useLocation();
  useTabShortcuts(tabs);

  return (
    <div className="flex min-h-screen flex-col">
      <TopBar tabs={tabs} />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 pb-24 pt-12 sm:px-6">
        {!data ? (
          <p className="py-24 font-serif text-lg text-muted">Loading…</p>
        ) : (
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.22, ease: [0.2, 0.7, 0.2, 1] }}
            >
              <Routes location={location}>
                {tabs.map((t) => (
                  <Route key={t.id} path={`/${t.id}`} element={<t.component />} />
                ))}
                <Route path="*" element={<Navigate to={`/${tabs[0].id}`} replace />} />
              </Routes>
            </motion.div>
          </AnimatePresence>
        )}
      </main>
      <Footer />
    </div>
  );
}

function Footer() {
  const { data } = useApp();
  return (
    <footer className="border-t border-rule">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-1 px-4 py-5 text-xs text-muted sm:px-6">
        <span className="font-serif text-sm text-ink">ProDefenders</span>
        <span>ITFest 2026 prototype</span>
        <span>
          {data?.source === "api"
            ? "Connected to the ProDefenders API"
            : data?.source === "live"
              ? "Videos and data from output/ (API not running)"
              : "Sample data: no rendered clip found"}
        </span>
        <span className="ml-auto hidden sm:inline">Keys 1–4 switch tabs</span>
      </div>
    </footer>
  );
}

/** Tastele 1–9 deschid tabul corespunzător (ignorate cât timp scrii într-un câmp). */
function useTabShortcuts(tabs: TabDef[]) {
  const navigate = useNavigate();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (e.ctrlKey || e.metaKey || e.altKey || el.closest("input, textarea, select, [contenteditable]")) return;
      const n = Number(e.key);
      if (n >= 1 && n <= tabs.length) navigate(`/${tabs[n - 1].id}`);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tabs, navigate]);
}
