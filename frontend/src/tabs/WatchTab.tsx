import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useApp, useClip } from "../state";
import { assetUrl } from "../data/loadClip";
import { regionName, regionStyle } from "../regions";
import { ScreenPlaceholder, Transport, useSyncedVideos } from "../components/video";
import { AdCreative, CountryMark, PageHeader, Section, Toggle, compact, dec } from "../components/ui";

export default function WatchTab() {
  const { clips, clip, setClip } = useApp();
  return (
    <>
      <PageHeader
        eyebrow="For viewers"
        title="Watch"
        lede="One scene, localised for every market. Pick a country to see the version its viewers get: the same footage, with a local brand on the billboard."
        aside={
          <label className="text-sm">
            <span className="mb-1.5 block text-xs uppercase tracking-[0.14em] text-muted">Video</span>
            <select
              value={clip}
              onChange={(e) => setClip(e.target.value)}
              className="min-w-48 border border-rule-strong bg-card px-3 py-2 capitalize outline-none focus:border-ink"
            >
              {clips.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
        }
      />
      {/* key: la schimbarea clipului playerul pornește de la zero */}
      <Player key={clip} />
    </>
  );
}

function Player() {
  const { manifest, ads } = useClip();
  const { region, setRegion } = useApp();
  const [aiOn, setAiOn] = useState(false);
  const regions = manifest.regions;
  const active = Math.max(0, regions.findIndex((r) => r.code === region));
  const current = regions[active];
  const aiIndex = regions.length; // AI view e ultimul video din grup
  const group = useSyncedVideos(active);
  const shown = aiOn ? aiIndex : active;
  const ad = ads?.find((a) => a.id === current.ad_id);
  const adFor = (id?: string) => ads?.find((a) => a.id === id);

  return (
    <>
      <div className="relative aspect-video overflow-hidden bg-screen">
        {regions.map((r, i) => (
          <video
            key={r.code}
            {...group.bind(i)}
            src={assetUrl(r.video)}
            className="absolute inset-0 h-full w-full object-cover transition-opacity duration-300"
            style={{ opacity: shown === i ? 1 : 0 }}
          />
        ))}
        {manifest.ai_view && (
          <video
            {...group.bind(aiIndex)}
            src={assetUrl(manifest.ai_view)}
            className="absolute inset-0 h-full w-full object-cover transition-opacity duration-300"
            style={{ opacity: aiOn ? 1 : 0 }}
          />
        )}
        {group.failed[shown] && <ScreenPlaceholder path={aiOn ? manifest.ai_view : current.video} />}
        <AnimatePresence mode="wait">
          <motion.div
            key={aiOn ? "ai" : current.code}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="absolute bottom-4 left-4 flex items-center gap-2 bg-paper/95 px-3 py-1.5 text-xs font-medium"
          >
            {aiOn ? (
              "What the AI sees"
            ) : (
              <>
                <CountryMark code={current.code} label={current.label} /> version
              </>
            )}
          </motion.div>
        </AnimatePresence>
      </div>

      <Transport group={group} disabled={regions.every((_, i) => group.failed[i])}>
        {manifest.ai_view && <Toggle checked={aiOn} onChange={setAiOn} label="Show what the AI sees" />}
      </Transport>

      <div className="mt-8">
        <p className="text-xs uppercase tracking-[0.14em] text-muted">Viewer's country</p>
        <div className="mt-3 grid gap-x-6 gap-y-4 sm:grid-cols-3">
          {regions.map((r) => {
            const isActive = r.code === current.code;
            const a = adFor(r.ad_id);
            return (
              <button
                key={r.code}
                onClick={() => setRegion(r.code)}
                aria-pressed={isActive}
                className={`relative border-t pt-4 text-left transition-colors ${isActive ? "border-transparent" : "border-rule hover:border-rule-strong"}`}
              >
                {isActive && (
                  <motion.span
                    layoutId="country-rule"
                    className="absolute inset-x-0 -top-px h-[3px]"
                    style={{ background: regionStyle(r.code).color }}
                    transition={{ duration: 0.3, ease: [0.2, 0.7, 0.2, 1] }}
                  />
                )}
                <CountryMark code={r.code} label={r.label} muted={!isActive} />
                <p className={`mt-1.5 font-serif text-xl ${isActive ? "" : "text-ink-2"}`}>{a?.brand ?? r.ad_id ?? "No placement"}</p>
                {a && <p className="text-sm text-muted">{a.headline} · {a.price}</p>}
              </button>
            );
          })}
        </div>
      </div>

      <Section title="On the billboard" aside={`${regionName(current.code, current.label)} version`}>
        <AnimatePresence mode="wait">
          <motion.div
            key={current.code}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="grid gap-10 md:grid-cols-[320px_minmax(0,1fr)]"
          >
            {ad ? <AdCreative ad={ad} /> : <div className="grid aspect-[2/1] place-items-center border border-rule text-sm text-muted">No creative on file</div>}
            <div>
              {current.reason && (
                <blockquote className="border-l-2 border-ink pl-5 font-serif text-xl italic leading-relaxed text-ink-2">{current.reason}</blockquote>
              )}
              <p className="mt-2 pl-5 text-xs text-muted">Why the AI chose this ad for the scene</p>
              <dl className="mt-8 grid grid-cols-3 gap-6">
                <Fact label="On screen" value={current.metrics?.screen_time_sec !== undefined ? `${dec(current.metrics.screen_time_sec)} s` : "—"} />
                <Fact label="Visibility" value={current.metrics?.visibility !== undefined ? `${dec(current.metrics.visibility)} / 10` : "—"} />
                <Fact label="Est. audience" value={current.metrics?.est_impressions !== undefined ? compact(current.metrics.est_impressions) : "—"} />
              </dl>
            </div>
          </motion.div>
        </AnimatePresence>
      </Section>
    </>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-t border-rule pt-2">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-1 font-serif text-2xl tabular-nums">{value}</dd>
    </div>
  );
}
