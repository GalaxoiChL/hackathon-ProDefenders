// De unde vin datele unui clip, în ordine: serverul din backend/ (API), fișierele din output/, apoi datele de test.
import type { Ad, ClipData, Manifest, ManifestRegion, Scene, Surface, Surfaces, Viewer } from "./types";
import mockManifest from "./mock/melbourne.manifest.json";
import mockScene from "./mock/melbourne.scene.json";
import mockSurfaces from "./mock/melbourne.surfaces.json";
import mockAds from "./mock/ads.json";

/** Căile din manifest sunt relative la rădăcina repo-ului; vite.config.ts (sau backend-ul) le servește la "/". */
export const assetUrl = (p: string) => "/" + p.replace(/^\/+/, "");

async function fetchJson<T>(path: string, timeoutMs = 8000): Promise<T | undefined> {
  try {
    const res = await fetch(assetUrl(path), { cache: "no-store", signal: AbortSignal.timeout(timeoutMs) });
    if (!res.ok) return undefined;
    return (await res.json()) as T; // un fișier lipsă primește index.html de la Vite, deci json() aruncă
  } catch {
    return undefined;
  }
}

let apiCheck: Promise<boolean> | undefined;

/** Răspunde serverul din backend/? (în dev, Vite trimite /api spre el; vezi vite.config.ts). Verificat o singură dată. */
export function apiAvailable(): Promise<boolean> {
  apiCheck ??= fetchJson<{ status?: string }>("api/health", 1500).then((h) => h?.status === "ok");
  return apiCheck;
}

/** Manifestul așa cum îl scriu pipeline/run.py sau backend-ul, înainte de normalizare. */
interface RawManifest extends Omit<Manifest, "scene" | "surfaces" | "regions"> {
  source?: string;
  ai_view_url?: string;
  scene?: string | Scene | null;
  surfaces?: string | Surface[] | null;
  regions: (ManifestRegion & { video_url?: string })[];
}

/** Aduce orice variantă de manifest la forma din types.ts; scena și suprafețele puse direct în manifest sunt scoase separat. */
function normalize(raw: RawManifest): { manifest: Manifest; scene?: Scene; surfaces?: Surfaces } {
  const { scene, surfaces, source, ai_view_url, regions, ...rest } = raw;
  const manifest: Manifest = {
    ...rest,
    // clipul sursă stă în assets/clips/ (CLAUDE.md); manifestul sintetizat de backend nu îl menționează
    original: rest.original ?? source ?? `assets/clips/${raw.clip}.mp4`,
    ai_view: ai_view_url ?? rest.ai_view,
    scene: typeof scene === "string" ? scene : undefined,
    surfaces: typeof surfaces === "string" ? surfaces : undefined,
    regions: regions.map(({ video_url, ...r }) => ({ ...r, label: r.label ?? r.code, video: video_url ?? r.video })),
  };
  return {
    manifest,
    scene: scene && typeof scene === "object" ? { ...scene, clip: scene.clip ?? raw.clip } : undefined,
    surfaces: Array.isArray(surfaces) ? { clip: raw.clip, surfaces } : undefined,
  };
}

/** Răspunsul de la GET /api/clips/{clip}/stats (doar câmpurile folosite). */
interface ApiStats {
  video?: { frames?: number; fps?: number; duration_s?: number; width?: number; height?: number };
  visibility?: { visible_seconds?: number };
  regions?: { code: string; impressions?: number; revenue_usd?: number }[];
}

function applyStats(m: Manifest, stats: ApiStats | undefined) {
  if (!stats) return;
  m.duration_sec ??= stats.video?.duration_s;
  m.fps ??= stats.video?.fps;
  m.stats = { frames: stats.video?.frames, ...m.stats };
  for (const r of m.regions) {
    const s = stats.regions?.find((x) => x.code === r.code);
    r.metrics = {
      screen_time_sec: stats.visibility?.visible_seconds,
      est_impressions: s?.impressions,
      est_revenue_usd: s?.revenue_usd,
      ...r.metrics,
    };
  }
}

/** Lista clipurilor: din API, apoi output/index.json ({"clips": [...]}), altfel clipul de test. */
export async function listClips(): Promise<string[]> {
  if (await apiAvailable()) {
    const clips = await fetchJson<{ clip: string }[]>("api/clips");
    if (clips?.length) return clips.map((c) => c.clip);
  }
  const index = await fetchJson<{ clips?: string[] }>("output/index.json");
  return index?.clips?.length ? index.clips : ["melbourne"];
}

export async function loadClip(clip: string): Promise<ClipData> {
  if (await apiAvailable()) {
    const raw = await fetchJson<RawManifest>(`api/clips/${clip}`);
    if (raw?.regions?.length) {
      const n = normalize(raw);
      const [scene, surfaces, ads, stats, play] = await Promise.all([
        n.scene ?? fetchJson<Scene>(`api/clips/${clip}/scene`),
        n.surfaces ?? fetchJson<Surfaces>(`api/clips/${clip}/surfaces`),
        fetchJson<{ ads: Ad[] }>("api/ads"),
        fetchJson<ApiStats>(`api/clips/${clip}/stats`),
        fetchJson<{ viewer?: Viewer }>(`api/clips/${clip}/play`),
      ]);
      applyStats(n.manifest, stats);
      return { manifest: n.manifest, scene, surfaces, ads: ads?.ads, viewer: play?.viewer, source: "api" };
    }
  }

  const raw = await fetchJson<RawManifest>(`output/${clip}.manifest.json`);
  if (raw?.regions?.length) {
    const n = normalize(raw);
    const [scene, surfaces, ads] = await Promise.all([
      n.scene ?? fetchJson<Scene>(n.manifest.scene ?? `output/${clip}.scene.json`),
      n.surfaces ??
        fetchJson<Surfaces>(n.manifest.surfaces ?? `output/${clip}.surfaces.json`).then(
          (s) => s ?? fetchJson<Surfaces>(`assets/clips/${clip}.surfaces.json`),
        ),
      fetchJson<Ad[]>("data/ads.json"),
    ]);
    return { manifest: n.manifest, scene, surfaces, ads, source: "live" };
  }

  return {
    manifest: mockManifest as unknown as Manifest,
    scene: mockScene as unknown as Scene,
    surfaces: mockSurfaces as unknown as Surfaces,
    ads: mockAds as unknown as Ad[],
    source: "mock",
  };
}
