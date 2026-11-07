import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useApp, useClip } from "../state";
import { assetUrl } from "../data/loadClip";
import { regionName } from "../regions";
import type { Ad, ManifestRegion, Viewer } from "../data/types";
import { CountryPicker } from "../components/CountryPicker";
import { ScreenPlaceholder, Transport, useSyncedVideos } from "../components/video";
import { AdCreative, CountryMark, PageHeader, Section, Toggle, compact, dec } from "../components/ui";

// fără ad_id (manifest sintetizat de backend) folosim prima reclamă a țării, ca pipeline/run.py
const adFor = (r: ManifestRegion, ads?: Ad[]) =>
  ads?.find((a) => a.id === r.ad_id) ?? (r.ad_id ? undefined : ads?.find((a) => a.region === r.code));
const brandOf = (r: ManifestRegion, ads?: Ad[]) => adFor(r, ads)?.brand ?? r.brand ?? r.ad_id;

export default function WatchTab() {
  const { clips, clip, setClip, region, setRegion } = useApp();
  const { manifest, ads } = useClip();
  return (
    <>
      <PageHeader
        eyebrow="For viewers"
        title="Watch"
        lede="One scene, localised for every market. Pick a country to see the version its viewers get: the same footage, with a local brand on the billboard."
        aside={
          <div className="flex flex-wrap items-end gap-4">
            <label className="text-sm">
              <span className="mb-1.5 block text-xs uppercase tracking-[0.14em] text-muted">Video</span>
              <select
                value={clip}
                onChange={(e) => setClip(e.target.value)}
                className="min-w-44 border border-rule-strong bg-card px-3 py-2 capitalize outline-none focus:border-ink"
              >
                {clips.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <div className="text-sm">
              <span className="mb-1.5 block text-xs uppercase tracking-[0.14em] text-muted">Country</span>
              <CountryPicker
                value={region ?? manifest.regions[0]?.code}
                onChange={setRegion}
                options={manifest.regions.map((r) => ({ code: r.code, label: r.label, detail: brandOf(r, ads) }))}
              />
            </div>
          </div>
        }
      />
      {/* key: la schimbarea clipului playerul pornește de la zero */}
      <Player key={clip} />
    </>
  );
}

const MATCH_TEXT: Record<string, string> = {
  exact: "",
  language: "closest version by language",
  subregion: "closest version in your region",
  continent: "closest version on your continent",
  default: "default version",
};

function ViewerNote({ viewer, shown }: { viewer: Viewer; shown: ManifestRegion }) {
  const detected = viewer.source === "ip" || viewer.source === "cloudflare";
  const country = regionName(viewer.country, viewer.name);
  const match = MATCH_TEXT[viewer.match ?? "exact"];
  let text = detected
    ? `Your location: ${country}${viewer.region !== viewer.country && match ? `, so you get the ${match}` : ""}.`
    : `Location not detected (local network), so the ${regionName(viewer.region)} version is the default.`;
  if (viewer.region !== shown.code) text += ` You are now viewing the ${regionName(shown.code, shown.label)} version.`;
  return <p className="mt-3 text-xs text-muted">{text}</p>;
}

function Player() {
  const { manifest, ads, viewer } = useClip();
  const { region } = useApp();
  const [aiOn, setAiOn] = useState(false);
  const regions = manifest.regions;
  const active = Math.max(0, regions.findIndex((r) => r.code === region));
  const current = regions[active];
  const aiIndex = regions.length; // AI view e ultimul video din grup
  const group = useSyncedVideos(active);

  // Cu 15 piețe nu încărcăm toate versiunile: o țară se încarcă prima oară când e aleasă, apoi rămâne sincronizată.
  const [mounted, setMounted] = useState(() => new Set([active]));
  useEffect(() => setMounted((m) => (m.has(active) ? m : new Set(m).add(active))), [active]);

  // Până se încarcă versiunea nouă rămâne pe ecran cea veche, ca să nu clipească negru.
  const lastShown = useRef(active);
  const regionShown = group.ready[active] || group.failed[active] ? active : lastShown.current;
  useEffect(() => {
    lastShown.current = regionShown;
  }, [regionShown]);
  const shown = aiOn ? aiIndex : regionShown;

  const ad = adFor(current, ads);
  const brand = brandOf(current, ads);

  return (
    <>
      <div className="relative aspect-video overflow-hidden bg-screen">
        {regions.map((r, i) =>
          mounted.has(i) ? (
            <video
              key={r.code}
              {...group.bind(i)}
              src={assetUrl(r.video)}
              className="absolute inset-0 h-full w-full object-cover transition-opacity duration-300"
              style={{ opacity: shown === i ? 1 : 0 }}
            />
          ) : null,
        )}
        {manifest.ai_view && (
          <video
            {...group.bind(aiIndex)}
            src={assetUrl(manifest.ai_view)}
            className="absolute inset-0 h-full w-full object-cover transition-opacity duration-300"
            style={{ opacity: aiOn ? 1 : 0 }}
          />
        )}
        {group.failed[shown] && <ScreenPlaceholder path={aiOn ? manifest.ai_view : regions[shown]?.video} />}
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

      <Transport group={group} disabled={[...mounted].every((i) => group.failed[i])}>
        {manifest.ai_view && <Toggle checked={aiOn} onChange={setAiOn} label="Show what the AI sees" />}
      </Transport>
      {viewer && <ViewerNote viewer={viewer} shown={current} />}

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
            <div>
              {current.creative ? (
                <img src={assetUrl(current.creative)} alt={`${brand ?? "Ad"} creative`} className="max-h-96 w-full bg-card object-contain" />
              ) : ad ? (
                <AdCreative ad={ad} />
              ) : (
                <div className="grid aspect-[2/1] place-items-center border border-rule text-sm text-muted">No creative on file</div>
              )}
              {current.creative && <p className="mt-2 text-xs text-muted">The creative as placed on the billboard</p>}
            </div>
            <div>
              <p className="font-serif text-2xl">{brand ?? "No placement"}</p>
              {current.reason && (
                <blockquote className="mt-4 border-l-2 border-ink pl-5 font-serif text-xl italic leading-relaxed text-ink-2">{current.reason}</blockquote>
              )}
              {current.reason && <p className="mt-2 pl-5 text-xs text-muted">Why this ad was chosen for the scene</p>}
              <dl className="mt-8 grid grid-cols-3 gap-6">
                <Fact label="On screen" value={current.metrics?.screen_time_sec !== undefined ? `${dec(current.metrics.screen_time_sec)} s` : "—"} />
                <Fact label="Visibility" value={current.metrics?.visibility !== undefined ? `${dec(current.metrics.visibility)} / 10` : "—"} />
                <Fact label="Est. impressions" value={current.metrics?.est_impressions !== undefined ? compact(current.metrics.est_impressions) : "—"} />
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
