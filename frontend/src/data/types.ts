// Tipuri care oglindesc contractele JSON din CLAUDE.md.
// Contractul minim al manifestului e obligatoriu; tot restul e opțional (vezi PLAN.md, secțiunea 7.2).

export type RegionCode = string;

export interface RegionMetrics {
  screen_time_sec?: number;
  visibility?: number;
  est_impressions?: number;
  est_revenue_eur?: number;
  est_revenue_usd?: number;
}

export interface ManifestRegion {
  code: RegionCode;
  label: string;
  video: string;
  ad_id?: string;
  /** scris de pipeline/run.py */
  brand?: string;
  /** imaginea lipită pe panou pentru țara asta (run.py) */
  creative?: string;
  reason?: string;
  ad_image?: string;
  metrics?: RegionMetrics;
}

export interface PipelineStep {
  step: string;
  status: "done" | "running" | "missing" | "error";
  sec?: number;
}

export interface TimelinePoint {
  frame: number;
  state: "visible" | "lost" | "occluded";
}

export interface Manifest {
  clip: string;
  ai_view?: string;
  regions: ManifestRegion[];
  original?: string;
  /** video cu toate țările una lângă alta (run.py) */
  compare?: string;
  poster?: string;
  duration_sec?: number;
  fps?: number;
  width?: number;
  height?: number;
  scene?: string;
  surfaces?: string;
  stats?: { frames?: number; lost_frames?: number; sec_per_frame?: number; occluded_frames?: number };
  timeline?: TimelinePoint[];
  pipeline?: PipelineStep[];
}

export interface Scene {
  clip: string;
  location?: string;
  time_of_day?: string;
  weather?: string;
  mood?: string;
  brand_safety?: { safe: boolean; reasons: string[] };
  choices?: Record<RegionCode, { ad_id: string; reason: string }>;
}

export interface Surface {
  id: string;
  type: string;
  frame: number;
  corners: [number, number][];
  aspect?: number;
  confidence?: number;
}

export interface Surfaces {
  clip: string;
  surfaces: Surface[];
}

export interface Ad {
  id: string;
  region: RegionCode;
  brand: string;
  category?: string;
  headline?: string;
  price?: string;
  colors?: { bg: string; fg?: string; accent?: string };
  product_image?: string;
  /** reclama reală a brandului (imagine; nu e în git, se descarcă de la creative_source) */
  creative?: string;
  creative_source?: string;
  description?: string;
  fits?: string[];
  avoid?: string[];
}

/** Țara privitorului, după geolocația din backend (GET /api/clips/{clip}/play). */
export interface Viewer {
  country: string;
  name?: string;
  /** versiunea aleasă pentru el */
  region: RegionCode;
  /** exact | language | subregion | continent | default */
  match?: string;
  /** query | header | cloudflare | ip | default */
  source?: string;
}

/** Tot ce știe UI-ul despre un clip, deja normalizat. */
export interface ClipData {
  manifest: Manifest;
  scene?: Scene;
  surfaces?: Surfaces;
  ads?: Ad[];
  viewer?: Viewer;
  /** "api" = serverul din backend/; "live" = fișiere din output/; "mock" = date de test din src/data/mock */
  source: "api" | "live" | "mock";
}

// Marketplace (încă nu e în CLAUDE.md: data/inventory.json și data/bids.json)

/** Un spațiu de vânzare: un panou dintr-un clip, într-o țară. */
export interface Slot {
  id: string;
  clip: string;
  surface_id: string;
  region: RegionCode;
  title: string;
  /** Categoriile de produse acceptate de proprietarul conținutului. */
  categories?: string[];
  /** Descrierea scenei, comparată cu `avoid` din ads.json (brand safety). */
  tags?: string[];
  screen_time_sec?: number;
  visibility?: number;
  audience: number;
  /** CPM în moneda spațiului */
  cpm: number;
  /** EUR în datele de test, USD în backend */
  currency: "EUR" | "USD";
  /** preț minim dat de backend; fără el se calculează (auction.ts) */
  floor?: number;
  /** "open" fără termen = licitație deschisă până o închide cineva (backend) */
  status?: "open" | "closed";
  /** Secunde până se închide licitația, de la încărcarea paginii; lipsă și fără status = deja închisă. */
  closes_in_sec?: number;
  thumbnail?: string;
}

export interface Bid {
  id: string;
  slot_id: string;
  /** id-ul companiei: din ads.json în datele de test, sintetizat pentru ofertele din backend */
  brand_id: string;
  /** în moneda spațiului */
  amount: number;
  placed_at: string;
  message?: string;
}
