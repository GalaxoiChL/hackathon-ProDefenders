import type { Ad, ClipData, Manifest, Scene, Surfaces } from "./types";
import mockManifest from "./mock/melbourne.manifest.json";
import mockScene from "./mock/melbourne.scene.json";
import mockSurfaces from "./mock/melbourne.surfaces.json";
import mockAds from "./mock/ads.json";

/** Căile din manifest sunt relative la rădăcina repo-ului; vite.config.ts le servește la "/". */
export const assetUrl = (p: string) => "/" + p.replace(/^\/+/, "");

async function fetchJson<T>(path: string): Promise<T | undefined> {
  try {
    const res = await fetch(assetUrl(path), { cache: "no-store" });
    if (!res.ok) return undefined;
    return (await res.json()) as T; // un fișier lipsă primește index.html de la Vite, deci json() aruncă
  } catch {
    return undefined;
  }
}

/** Lista clipurilor: output/index.json ({"clips": [...]}) dacă există, altfel clipul de test. */
export async function listClips(): Promise<string[]> {
  const index = await fetchJson<{ clips?: string[] }>("output/index.json");
  return index?.clips?.length ? index.clips : ["melbourne"];
}

export async function loadClip(clip: string): Promise<ClipData> {
  const manifest = await fetchJson<Manifest>(`output/${clip}.manifest.json`);
  if (!manifest?.regions?.length) {
    return {
      manifest: mockManifest as unknown as Manifest,
      scene: mockScene as unknown as Scene,
      surfaces: mockSurfaces as unknown as Surfaces,
      ads: mockAds as unknown as Ad[],
      source: "mock",
    };
  }
  const [scene, surfaces, ads] = await Promise.all([
    fetchJson<Scene>(manifest.scene ?? `output/${clip}.scene.json`),
    fetchJson<Surfaces>(manifest.surfaces ?? `assets/clips/${clip}.surfaces.json`),
    fetchJson<Ad[]>("data/ads.json"),
  ]);
  return { manifest, scene, surfaces, ads, source: "live" };
}
