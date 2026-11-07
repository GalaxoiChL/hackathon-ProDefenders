// Încarcă un video și reclamele tale, marchează panoul și vezi rezultatul pe loc. Totul rulează în browser:
// nimic nu pleacă de pe laptop și nu trebuie instalat nimic (fără Python, fără backend).
import { useCallback, useEffect, useRef, useState, type ChangeEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Plus, Trash2, Upload as UploadIcon } from "lucide-react";
import { useApp } from "../state";
import { KNOWN_REGIONS, regionName } from "../regions";
import type { Ad, ClipData, Manifest } from "../data/types";
import { CountryPicker, Dropdown } from "../components/CountryPicker";
import { Button, PageHeader, Section, Toggle } from "../components/ui";
import { CornerPicker } from "../upload/CornerPicker";
import { Compositor } from "../upload/Compositor";
import type { Point } from "../upload/homography";

/** Peste atât, exportul (care rulează în timp real) devine lung. */
const LONG_CLIP_SEC = 20;

interface VideoInfo {
  url: string;
  name: string;
  width: number;
  height: number;
  duration: number;
  frame: string;
}

interface AdRow {
  id: number;
  code: string;
  brand: string;
  url?: string;
  img?: HTMLImageElement;
}

interface Rendered {
  code: string;
  url: string;
}

const RECORD_TYPES = ["video/mp4;codecs=avc1", "video/mp4", "video/webm;codecs=vp9", "video/webm"];
const recordType = () => (typeof MediaRecorder === "undefined" ? undefined : RECORD_TYPES.find((t) => MediaRecorder.isTypeSupported(t)));
const extensionOf = (type: string) => (type.startsWith("video/mp4") ? "mp4" : "webm");

const once = (el: HTMLElement, event: string) => new Promise<void>((resolve) => el.addEventListener(event, () => resolve(), { once: true }));

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("This image could not be read"));
    img.src = url;
  });
}

/** Primul cadru ca imagine, pentru marcarea colțurilor. */
async function readVideo(file: File): Promise<VideoInfo> {
  const url = URL.createObjectURL(file);
  const v = document.createElement("video");
  v.muted = true;
  v.preload = "auto";
  v.src = url;
  await Promise.race([
    once(v, "loadeddata"),
    once(v, "error").then(() => {
      throw new Error("This video format can't be played in the browser. Try an MP4 (H.264).");
    }),
  ]);
  v.currentTime = Math.min(0.05, v.duration / 2);
  await once(v, "seeked");
  const c = document.createElement("canvas");
  c.width = v.videoWidth;
  c.height = v.videoHeight;
  c.getContext("2d")!.drawImage(v, 0, 0);
  return {
    url,
    name: file.name.replace(/\.[^.]+$/, ""),
    width: v.videoWidth,
    height: v.videoHeight,
    duration: v.duration,
    frame: c.toDataURL("image/jpeg", 0.85),
  };
}

const clipName = (name: string) =>
  `upload-${name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 32) || "clip"}`;

export default function UploadTab() {
  const { addSessionClip } = useApp();
  const navigate = useNavigate();
  const [video, setVideo] = useState<VideoInfo | null>(null);
  const [videoError, setVideoError] = useState<string | null>(null);
  const [ads, setAds] = useState<AdRow[]>([{ id: 1, code: "RO", brand: "" }]);
  const [corners, setCorners] = useState<Point[]>([]);
  const ready = !!video && corners.length === 4 && ads.some((a) => a.img);

  const pickVideo = async (file?: File) => {
    if (!file) return;
    setVideoError(null);
    try {
      if (video) URL.revokeObjectURL(video.url);
      setVideo(await readVideo(file));
      setCorners([]);
    } catch (e) {
      setVideoError((e as Error).message);
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="Try it yourself"
        title="Upload"
        lede="Put your own ad on a billboard in your own video. Everything runs in this browser: nothing is uploaded anywhere and nothing needs to be installed."
      />

      <Step n={1} title="Your video" done={!!video}>
        <DropZone onFile={pickVideo} accept="video/*" label={video ? `${video.name} · ${video.width}×${video.height} · ${video.duration.toFixed(1)} s` : "Drop a video here, or click to choose one"} />
        {videoError && <p className="mt-2 text-sm text-accent">{videoError}</p>}
        <p className="mt-2 text-xs text-muted">Best results with a camera that stays still. MP4 works everywhere; keep it short, the export runs in real time.</p>
        {video && video.duration > LONG_CLIP_SEC && (
          <p className="mt-2 text-sm text-accent">
            This clip is {Math.round(video.duration)} s long. Exporting takes about that long for every country.
          </p>
        )}
      </Step>

      <Step n={2} title="Your ads" done={ads.some((a) => a.img)}>
        <AdRows ads={ads} setAds={setAds} />
      </Step>

      <Step n={3} title="Mark the billboard" done={corners.length === 4} disabled={!video} hint="Choose a video first.">
        {video && <CornerPicker frame={video.frame} aspect={video.width / video.height} corners={corners} onChange={setCorners} />}
      </Step>

      <Step n={4} title="Preview and export" done={false} disabled={!ready} hint="Needs a video, at least one ad image and all four corners.">
        {ready && video && (
          <Preview
            video={video}
            ads={ads.filter((a) => a.img)}
            corners={corners}
            onOpen={(rendered) => {
              const name = clipName(video.name);
              const manifest: Manifest = {
                clip: name,
                original: video.url,
                ai_view: rendered.find((r) => r.code === "AI")?.url,
                regions: rendered
                  .filter((r) => r.code !== "AI")
                  .map((r) => {
                    const ad = ads.find((a) => a.code === r.code);
                    return { code: r.code, label: regionName(r.code), video: r.url, ad_id: `${name}-${r.code}`, brand: ad?.brand || "Your brand" };
                  }),
              };
              const clipAds: Ad[] = ads
                .filter((a) => a.img)
                .map((a) => ({ id: `${name}-${a.code}`, region: a.code, brand: a.brand || "Your brand", creative: a.url }));
              const data: ClipData = { manifest, ads: clipAds, source: "session" };
              addSessionClip(data);
              navigate("/watch");
            }}
          />
        )}
      </Step>
    </>
  );
}

function Step({
  n,
  title,
  done,
  disabled,
  hint,
  children,
}: {
  n: number;
  title: string;
  done: boolean;
  disabled?: boolean;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <Section
      title={`${n}. ${title}`}
      aside={done ? <span className="text-positive">Done</span> : undefined}
      className={disabled ? "opacity-60" : ""}
    >
      {disabled ? <p className="text-sm text-muted">{hint}</p> : children}
    </Section>
  );
}

function DropZone({ onFile, accept, label, compact }: { onFile: (f?: File) => void; accept: string; label: string; compact?: boolean }) {
  const [over, setOver] = useState(false);
  return (
    <label
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        onFile(e.dataTransfer.files[0]);
      }}
      className={`flex cursor-pointer items-center gap-3 border border-dashed bg-card text-sm transition-colors ${
        compact ? "px-3 py-2" : "px-5 py-6"
      } ${over ? "border-ink" : "border-rule-strong hover:border-ink"}`}
    >
      <UploadIcon size={compact ? 15 : 18} className="shrink-0 text-muted" />
      <span className="min-w-0 truncate">{label}</span>
      <input type="file" accept={accept} className="sr-only" onChange={(e: ChangeEvent<HTMLInputElement>) => onFile(e.target.files?.[0] ?? undefined)} />
    </label>
  );
}

function AdRows({ ads, setAds }: { ads: AdRow[]; setAds: (fn: (a: AdRow[]) => AdRow[]) => void }) {
  const [error, setError] = useState<string | null>(null);
  const update = (id: number, fields: Partial<AdRow>) => setAds((list) => list.map((a) => (a.id === id ? { ...a, ...fields } : a)));
  const used = new Set(ads.map((a) => a.code));

  const pickImage = async (row: AdRow, file?: File) => {
    if (!file) return;
    setError(null);
    try {
      if (row.url) URL.revokeObjectURL(row.url);
      const url = URL.createObjectURL(file);
      update(row.id, { url, img: await loadImage(url), brand: row.brand || file.name.replace(/\.[^.]+$/, "") });
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div>
      <ul className="space-y-3">
        {ads.map((row) => (
          <li key={row.id} className="grid items-center gap-3 sm:grid-cols-[230px_minmax(0,1fr)_minmax(0,1.2fr)_auto]">
            <CountryPicker
              value={row.code}
              onChange={(code) => update(row.id, { code })}
              options={KNOWN_REGIONS.filter((c) => c === row.code || !used.has(c)).map((code) => ({ code }))}
            />
            <input
              value={row.brand}
              onChange={(e) => update(row.id, { brand: e.target.value })}
              placeholder="Brand name"
              className="border border-rule-strong bg-card px-3 py-2 text-sm outline-none focus:border-ink"
            />
            <div className="flex min-w-0 items-center gap-3">
              {row.url && <img src={row.url} alt="" className="h-10 w-14 shrink-0 border border-rule object-cover" />}
              <div className="min-w-0 flex-1">
                <DropZone compact accept="image/*" onFile={(f) => pickImage(row, f)} label={row.img ? "Change the ad image" : "Choose the ad image"} />
              </div>
            </div>
            <button
              type="button"
              onClick={() => setAds((list) => list.filter((a) => a.id !== row.id))}
              disabled={ads.length === 1}
              aria-label="Remove this country"
              className="justify-self-start p-2 text-muted hover:text-accent disabled:opacity-30"
            >
              <Trash2 size={16} />
            </button>
          </li>
        ))}
      </ul>
      {error && <p className="mt-2 text-sm text-accent">{error}</p>}
      {ads.length < KNOWN_REGIONS.length && (
        <button
          type="button"
          onClick={() =>
            setAds((list) => [...list, { id: Date.now(), code: KNOWN_REGIONS.find((c) => !used.has(c)) ?? "US", brand: "" }])
          }
          className="mt-4 inline-flex items-center gap-2 text-sm underline decoration-rule-strong underline-offset-4 hover:decoration-ink"
        >
          <Plus size={15} /> Add another country
        </button>
      )}
    </div>
  );
}

function Preview({ video, ads, corners, onOpen }: { video: VideoInfo; ads: AdRow[]; corners: Point[]; onOpen: (r: Rendered[]) => void }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const player = useRef<HTMLVideoElement>(null);
  const comp = useRef<Compositor | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [code, setCode] = useState(ads[0].code);
  const [outline, setOutline] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [exporting, setExporting] = useState<string | null>(null);
  const [rendered, setRendered] = useState<Rendered[]>([]);
  const type = recordType();
  const current = ads.find((a) => a.code === code) ?? ads[0];

  useEffect(() => {
    try {
      comp.current = new Compositor(canvas.current!);
      comp.current.resize(video.width, video.height);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [video]);

  useEffect(() => {
    comp.current?.setCorners(corners);
  }, [corners]);

  useEffect(() => {
    if (!exporting) comp.current?.setAd(current?.img ?? null);
  }, [current, exporting]);

  // desenăm la fiecare cadru afișat de browser, cât timp e deschis tabul
  const outlineRef = useRef(outline);
  outlineRef.current = outline;
  useEffect(() => {
    let raf = 0;
    const tick = () => {
      if (player.current) comp.current?.render(player.current, outlineRef.current);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  const toggle = () => {
    const v = player.current!;
    if (v.paused) {
      if (v.ended) v.currentTime = 0;
      void v.play();
    } else v.pause();
  };

  /** Înregistrează canvas-ul de la început până la sfârșit, cu reclama dată (sau doar conturul, pentru AI view). */
  const record = useCallback(
    async (img: HTMLImageElement | null, withOutline: boolean): Promise<string> => {
      const v = player.current!;
      const c = comp.current!;
      c.setAd(img);
      outlineRef.current = withOutline;
      v.pause();
      v.currentTime = 0;
      await once(v, "seeked");
      const stream = canvas.current!.captureStream(30);
      const rec = new MediaRecorder(stream, { mimeType: type, videoBitsPerSecond: 8_000_000 });
      const chunks: Blob[] = [];
      rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      const stopped = new Promise<void>((resolve) => (rec.onstop = () => resolve()));
      rec.start(250);
      await v.play();
      await once(v, "ended");
      rec.stop();
      await stopped;
      stream.getTracks().forEach((t) => t.stop());
      return URL.createObjectURL(new Blob(chunks, { type }));
    },
    [type],
  );

  const exportAll = async () => {
    if (!type) return;
    setError(null);
    rendered.forEach((r) => URL.revokeObjectURL(r.url));
    setRendered([]);
    const out: Rendered[] = [];
    try {
      for (const ad of ads) {
        setExporting(`Recording the ${regionName(ad.code)} version…`);
        out.push({ code: ad.code, url: await record(ad.img ?? null, false) });
      }
      setExporting("Recording the AI view…");
      out.push({ code: "AI", url: await record(null, true) });
      setRendered(out);
    } catch (e) {
      setError(`Recording failed: ${(e as Error).message}`);
    } finally {
      outlineRef.current = outline;
      comp.current?.setAd(current?.img ?? null);
      setExporting(null);
    }
  };

  return (
    <div>
      <div className="relative w-full overflow-hidden bg-screen" style={{ aspectRatio: String(video.width / video.height) }}>
        <canvas ref={canvas} className="absolute inset-0 h-full w-full" />
        {exporting && (
          <div className="absolute inset-x-0 bottom-0 bg-paper/95 px-4 py-2 text-sm">
            <span className="mr-2 inline-block size-1.5 animate-pulse rounded-full bg-accent align-middle" />
            {exporting}
          </div>
        )}
      </div>
      <video
        ref={player}
        src={video.url}
        muted
        playsInline
        preload="auto"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        className="pointer-events-none absolute h-px w-px opacity-0"
      />
      {error && <p className="mt-3 text-sm text-accent">{error}</p>}

      <div className="mt-4 flex flex-wrap items-center gap-4 border-b border-rule pb-4">
        <Button onClick={toggle} disabled={!!exporting}>
          {playing ? "Pause" : "Play"}
        </Button>
        <Dropdown
          label="Country"
          className="min-w-52"
          value={code}
          onChange={setCode}
          options={ads.map((a) => ({ value: a.code, label: regionName(a.code), detail: a.brand || undefined }))}
        />
        <Toggle checked={outline} onChange={setOutline} label="Show the billboard outline" disabled={!!exporting} />
      </div>

      <div className="mt-6">
        {type ? (
          <>
            <p className="text-sm text-ink-2">
              Export makes one video per country plus an AI view. It plays the clip once for each, in real time: about{" "}
              {Math.ceil((video.duration * (ads.length + 1)) / 5) * 5} seconds in total.
            </p>
            <div className="mt-4 flex flex-wrap gap-3">
              <Button onClick={exportAll} disabled={!!exporting}>
                {exporting ? "Exporting…" : rendered.length ? "Export again" : "Export videos"}
              </Button>
              {rendered.length > 0 && (
                <Button variant="secondary" onClick={() => onOpen(rendered)}>
                  Open in Watch and Compare
                </Button>
              )}
            </div>
          </>
        ) : (
          <p className="text-sm text-muted">This browser can't record video. The live preview above still works; use Chrome or Edge to export.</p>
        )}

        <AnimatePresence>
          {rendered.length > 0 && type && (
            <motion.ul initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="mt-6 border-t border-rule">
              {rendered.map((r) => (
                <li key={r.code} className="flex items-center justify-between gap-4 border-b border-rule py-3 text-sm">
                  <span>{r.code === "AI" ? "AI view (billboard outline)" : `${regionName(r.code)} version`}</span>
                  <a
                    href={r.url}
                    download={`${clipName(video.name)}_${r.code.toLowerCase()}.${extensionOf(type)}`}
                    className="underline decoration-rule-strong underline-offset-4 hover:decoration-ink"
                  >
                    Download .{extensionOf(type)}
                  </a>
                </li>
              ))}
            </motion.ul>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
