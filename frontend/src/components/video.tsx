// Mai multe videoclipuri care rulează ca unul singur: un video „master” dă timpul, celelalte îl urmează.
// Un video montat mai târziu (ex. o țară aleasă abia acum) se alătură automat la momentul curent.
import { useRef, useState, type CSSProperties, type ReactNode, type SyntheticEvent } from "react";
import { Pause, Play } from "lucide-react";

const DRIFT_SEC = 0.15;

export function useSyncedVideos(master: number) {
  const els = useRef<(HTMLVideoElement | null)[]>([]);
  const playingRef = useRef(false);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [failed, setFailed] = useState<Record<number, boolean>>({});
  const [ready, setReady] = useState<Record<number, boolean>>({});

  const all = () => els.current.filter((v): v is HTMLVideoElement => !!v && !Number.isNaN(v.duration));
  /** Masterul dă timpul; cât încă se încarcă, îl ține primul video gata. */
  const masterEl = () => {
    const m = els.current[master];
    return m && !Number.isNaN(m.duration) ? m : all()[0];
  };

  const setPlay = (p: boolean) => {
    playingRef.current = p;
    setPlaying(p);
  };
  const play = () => {
    const m = masterEl();
    if (!m) return;
    for (const v of all()) {
      v.currentTime = m.currentTime;
      void v.play().catch(() => {});
    }
    setPlay(true);
  };
  const pause = () => {
    all().forEach((v) => v.pause());
    setPlay(false);
  };
  const seek = (t: number) => {
    all().forEach((v) => (v.currentTime = t));
    setTime(t);
  };

  const bind = (i: number) => ({
    ref: (el: HTMLVideoElement | null) => {
      els.current[i] = el;
    },
    muted: i !== master,
    playsInline: true,
    preload: "auto" as const,
    onLoadedMetadata: (e: SyntheticEvent<HTMLVideoElement>) => {
      const el = e.currentTarget;
      setDuration((prev) => prev || el.duration);
      setFailed((f) => (f[i] ? { ...f, [i]: false } : f)); // sursa s-a schimbat și acum merge
      const m = masterEl();
      if (m && m !== el) {
        el.currentTime = m.currentTime;
        if (playingRef.current) void el.play().catch(() => {});
      }
    },
    onCanPlay: () => setReady((r) => (r[i] ? r : { ...r, [i]: true })),
    onTimeUpdate: (e: SyntheticEvent<HTMLVideoElement>) => {
      if (e.currentTarget !== masterEl()) return;
      const t = e.currentTarget.currentTime;
      setTime(t);
      for (const v of all()) if (v !== e.currentTarget && Math.abs(v.currentTime - t) > DRIFT_SEC) v.currentTime = t;
    },
    onEnded: (e: SyntheticEvent<HTMLVideoElement>) => e.currentTarget === masterEl() && setPlay(false),
    onError: () => setFailed((f) => ({ ...f, [i]: true })),
  });

  return { bind, playing, toggle: () => (playing ? pause() : play()), seek, time, duration, failed, ready };
}

export type SyncedVideos = ReturnType<typeof useSyncedVideos>;

const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

/** Play / pauză și bara de timp, comune unui grup sincronizat. */
export function Transport({ group, disabled, children }: { group: SyncedVideos; disabled?: boolean; children?: ReactNode }) {
  const { playing, toggle, seek, time, duration } = group;
  const progress = duration ? (time / duration) * 100 : 0;
  return (
    <div className="flex items-center gap-4 border-b border-rule py-3">
      <button
        onClick={toggle}
        disabled={disabled}
        aria-label={playing ? "Pause" : "Play"}
        className="grid size-9 shrink-0 place-items-center rounded-full bg-ink text-paper transition-colors hover:bg-ink-2 disabled:opacity-30"
      >
        {playing ? <Pause size={15} fill="currentColor" /> : <Play size={15} fill="currentColor" className="ml-0.5" />}
      </button>
      <input
        type="range"
        className="scrubber min-w-0 flex-1"
        min={0}
        max={duration || 1}
        step={0.01}
        value={time}
        disabled={disabled || !duration}
        onChange={(e) => seek(Number(e.target.value))}
        style={{ "--progress": `${progress}%` } as CSSProperties}
        aria-label="Seek"
      />
      <span className="shrink-0 font-mono text-xs tabular-nums text-muted">
        {clock(time)} / {clock(duration)}
      </span>
      {children}
    </div>
  );
}

/** Ce apare în locul unui video care nu a fost încă randat de pipeline. */
export function ScreenPlaceholder({ path, compact = false }: { path?: string; compact?: boolean }) {
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-screen px-6 text-center text-[#d9d5cc]">
      <p className={`font-serif ${compact ? "text-base" : "text-xl"}`}>Footage not rendered yet</p>
      {path && <p className="max-w-full truncate font-mono text-[11px] text-[#8f8a80]">{path}</p>}
      {!compact && <p className="text-xs text-[#8f8a80]">Generate it with backend/pipeline/insert_ad.py, then reload.</p>}
    </div>
  );
}
