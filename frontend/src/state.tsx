import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { listClips, loadClip, mediaIndexStamp } from "./data/loadClip";
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
  /** Un clip făcut în tabul Upload: trăiește doar în pagina deschisă, nu se salvează nicăieri. */
  addSessionClip: (data: ClipData) => void;
}

const AppContext = createContext<AppState | null>(null);

/** Cât de des verificăm media/index.json pentru clipuri noi. */
const MEDIA_CHECK_MS = 30_000;

export function AppProvider({ children }: { children: ReactNode }) {
  const [clips, setClips] = useState<string[]>(["melbourne"]);
  const [clip, setClip] = useState("melbourne");
  const [data, setData] = useState<ClipData | null>(null);
  const [loading, setLoading] = useState(true);
  const [region, setRegion] = useState<RegionCode | null>(null);
  const session = useRef<Record<string, ClipData>>({});

  // crește când apare sau s-a refăcut un clip publicat în media/, ca să reîncărcăm datele
  const [mediaVersion, setMediaVersion] = useState(0);

  useEffect(() => {
    listClips().then((list) => {
      const all = [...new Set([...list, ...Object.keys(session.current)])];
      setClips(all);
      setClip((c) => (all.includes(c) ? c : all[0]));
    });
  }, [mediaVersion]);

  // după un git pull, clipurile noi apar singure, fără reîncărcarea paginii
  useEffect(() => {
    let last: string | undefined;
    const check = () =>
      mediaIndexStamp().then((stamp) => {
        if (last !== undefined && stamp !== last) setMediaVersion((v) => v + 1);
        last = stamp;
      });
    check();
    const t = window.setInterval(check, MEDIA_CHECK_MS);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const own = session.current[clip];
    (own ? Promise.resolve(own) : loadClip(clip)).then((d) => {
      if (cancelled) return;
      setData(d);
      // păstrăm țara aleasă dacă există și în clipul nou; altfel cea detectată de backend după IP, apoi prima
      const has = (code?: string | null) => !!code && d.manifest.regions.some((x) => x.code === code);
      setRegion((r) => (has(r) ? r : has(d.viewer?.region) ? d.viewer!.region : d.manifest.regions[0]?.code ?? null));
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [clip, mediaVersion]);

  const addSessionClip = useCallback((d: ClipData) => {
    session.current[d.manifest.clip] = d;
    setClips((list) => (list.includes(d.manifest.clip) ? list : [...list, d.manifest.clip]));
    setClip(d.manifest.clip);
    setMediaVersion((v) => v + 1); // reîncarcă și dacă numele era deja ales
  }, []);

  return (
    <AppContext.Provider value={{ clips, clip, setClip, data, loading, region, setRegion, addSessionClip }}>{children}</AppContext.Provider>
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
