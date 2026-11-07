import { useState } from "react";
import { useApp, useClip } from "../state";
import { assetUrl } from "../data/loadClip";
import { regionName } from "../regions";
import { ScreenPlaceholder, Transport, useSyncedVideos } from "../components/video";
import { CountryMark, PageHeader, Section, Segmented } from "../components/ui";

export default function CompareTab() {
  const { clip } = useApp();
  return (
    <>
      <PageHeader
        eyebrow="Side by side"
        title="Compare"
        lede="Every market's version of the same scene, playing in sync. Only the billboard changes: the people, the camera and the light stay exactly as filmed."
      />
      <Grid key={`grid-${clip}`} />
      <BeforeAfter key={`ba-${clip}`} />
    </>
  );
}

const MAX_SIDE_BY_SIDE = 4;

function Grid() {
  const { manifest, ads } = useClip();
  const { region } = useApp();
  const regions = manifest.regions;
  // cu multe piețe (backend-ul are 15) comparăm doar câteva odată
  const [picked, setPicked] = useState<string[]>(() => {
    const codes = regions.map((r) => r.code);
    if (codes.length <= MAX_SIDE_BY_SIDE) return codes;
    return [...new Set([region ?? codes[0], ...codes])].slice(0, 3);
  });
  const toggle = (code: string) =>
    setPicked((p) =>
      p.includes(code) ? (p.length > 1 ? p.filter((c) => c !== code) : p) : p.length >= MAX_SIDE_BY_SIDE ? [...p.slice(1), code] : [...p, code],
    );
  const shown = regions.map((r, i) => ({ r, i })).filter(({ r }) => picked.includes(r.code));
  const group = useSyncedVideos(shown[0]?.i ?? 0);
  const cols = shown.length === 3 ? "lg:grid-cols-3" : "";

  return (
    <>
      {regions.length > MAX_SIDE_BY_SIDE && (
        <div className="mb-6">
          <p className="text-xs uppercase tracking-[0.14em] text-muted">Markets to compare · up to {MAX_SIDE_BY_SIDE}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {regions.map((r) => {
              const on = picked.includes(r.code);
              return (
                <button type="button"
                  key={r.code}
                  onClick={() => toggle(r.code)}
                  aria-pressed={on}
                  className={`border px-3 py-1.5 transition-colors ${on ? "border-ink bg-card" : "border-rule text-muted hover:border-rule-strong"}`}
                >
                  <CountryMark code={r.code} label={r.label} muted={!on} />
                </button>
              );
            })}
          </div>
        </div>
      )}
      <div className={`grid gap-6 sm:grid-cols-2 ${cols}`}>
        {shown.map(({ r, i }) => (
          <figure key={r.code}>
            <figcaption className="mb-2 flex items-baseline justify-between gap-3">
              <CountryMark code={r.code} label={r.label} />
              <span className="truncate font-serif text-[15px] text-ink-2">{(ads?.find((a) => a.id === r.ad_id) ?? (r.ad_id ? undefined : ads?.find((a) => a.region === r.code)))?.brand ?? r.brand ?? r.ad_id}</span>
            </figcaption>
            <div className="relative aspect-video overflow-hidden bg-screen">
              <video {...group.bind(i)} src={assetUrl(r.video)} className="absolute inset-0 h-full w-full object-cover" />
              {group.failed[i] && <ScreenPlaceholder path={r.video} compact />}
            </div>
          </figure>
        ))}
      </div>
      <div className="mt-2">
        <Transport group={group} disabled={shown.every(({ i }) => group.failed[i])} />
      </div>
    </>
  );
}

function BeforeAfter() {
  const { manifest } = useClip();
  const { region } = useApp();
  const [code, setCode] = useState(region ?? manifest.regions[0].code);
  const [split, setSplit] = useState(50);
  const group = useSyncedVideos(0);
  const after = manifest.regions.find((r) => r.code === code) ?? manifest.regions[0];

  return (
    <Section
      title="Before and after"
      aside={
        manifest.regions.length <= 4 ? (
          <Segmented
            id="before-after"
            label="Country"
            value={after.code}
            onChange={setCode}
            options={manifest.regions.map((r) => ({ value: r.code, label: regionName(r.code, r.label) }))}
          />
        ) : (
          <select
            value={after.code}
            onChange={(e) => setCode(e.target.value)}
            aria-label="Country"
            className="border border-rule-strong bg-card px-3 py-1.5 text-sm text-ink outline-none focus:border-ink"
          >
            {manifest.regions.map((r) => (
              <option key={r.code} value={r.code}>
                {regionName(r.code, r.label)}
              </option>
            ))}
          </select>
        )
      }
    >
      {!manifest.original ? (
        <p className="text-sm text-muted">The manifest does not list the original footage yet, so there is nothing to compare against.</p>
      ) : (
        <>
          <div className="relative aspect-video select-none overflow-hidden bg-screen">
            <video {...group.bind(0)} src={assetUrl(manifest.original)} className="absolute inset-0 h-full w-full object-cover" />
            <div className="absolute inset-0" style={{ clipPath: `inset(0 0 0 ${split}%)` }}>
              <video key={after.code} {...group.bind(1)} src={assetUrl(after.video)} className="absolute inset-0 h-full w-full object-cover" />
            </div>
            {group.failed[0] && group.failed[1] && <ScreenPlaceholder path={`${manifest.original}  ·  ${after.video}`} />}

            <div className="pointer-events-none absolute inset-y-0 w-px bg-paper" style={{ left: `${split}%` }}>
              <span className="absolute top-1/2 left-1/2 grid size-9 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-paper text-xs text-ink shadow">
                ⇆
              </span>
            </div>
            <span className="absolute top-4 left-4 bg-paper/95 px-2.5 py-1 text-xs font-medium">Original</span>
            <span className="absolute top-4 right-4 bg-paper/95 px-2.5 py-1 text-xs font-medium">{regionName(after.code, after.label)}</span>
            <input
              type="range"
              min={0}
              max={100}
              step={0.1}
              value={split}
              onChange={(e) => setSplit(Number(e.target.value))}
              aria-label="Move the divider between original and localised version"
              className="absolute inset-0 h-full w-full cursor-ew-resize opacity-0"
            />
          </div>
          <Transport group={group} disabled={group.failed[0] && group.failed[1]} />
        </>
      )}
    </Section>
  );
}
