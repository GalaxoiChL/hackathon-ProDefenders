import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { listClips, loadClip } from "./data/loadClip";
import type { ClipData, RegionCode } from "./data/types";

interface AppState {
  clips: string[];
  clip: string;
  setClip: (clip: string) => void;
  data: ClipData | null;
  loading: boolean;
  /** Țara curentă, comună tuturor taburilor. */
  region: RegionCode | null;
  setRegion: (code: RegionCode) => void;
}

const AppContext = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [clips, setClips] = useState<string[]>(["melbourne"]);
  const [clip, setClip] = useState("melbourne");
  const [data, setData] = useState<ClipData | null>(null);
  const [loading, setLoading] = useState(true);
  const [region, setRegion] = useState<RegionCode | null>(null);

  useEffect(() => {
    listClips().then((list) => {
      setClips(list);
      setClip((c) => (list.includes(c) ? c : list[0]));
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    loadClip(clip).then((d) => {
      if (cancelled) return;
      setData(d);
      // păstrăm țara aleasă dacă există și în clipul nou
      setRegion((r) => (r && d.manifest.regions.some((x) => x.code === r) ? r : d.manifest.regions[0]?.code ?? null));
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [clip]);

  return (
    <AppContext.Provider value={{ clips, clip, setClip, data, loading, region, setRegion }}>{children}</AppContext.Provider>
  );
}

export function useApp(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used inside <AppProvider>");
  return ctx;
}

/** Pentru taburi: datele clipului sunt garantat încărcate (App randează taburile doar după încărcare). */
export function useClip(): ClipData {
  const { data } = useApp();
  if (!data) throw new Error("useClip called before the clip data loaded");
  return data;
}
