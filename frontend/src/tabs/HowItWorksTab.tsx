// "How it works": the pipeline in six steps, then every service and model it relies on ("Powered by").
// The list mirrors the code: change it here when an integration is added or removed.
import { ArrowUpRight } from "lucide-react";
import { PageHeader, Section } from "../components/ui";

type Kind = "api" | "local" | "engine";

interface Integration {
  name: string;
  by: string;
  role: string;
  step: string;
  kind: Kind;
  url: string;
  optional?: boolean;
}

const STEPS = [
  { n: 1, title: "Find the ad space", text: "AI scans the footage and finds every billboard, poster, screen and bus ad, with its exact outline.", models: "OWLv2 · SAM 2" },
  { n: 2, title: "Understand the scene", text: "A vision model reads the place, time, weather and mood, and checks the scene is brand-safe.", models: "Gemma 3" },
  { n: 3, title: "Pick the ad", text: "For every country it chooses the real ad that fits the moment best, and says why.", models: "Gemma 3" },
  { n: 4, title: "Fit the creative", text: "The whole ad is kept; AI extends its background to the billboard's shape, then checks its own work.", models: "Stable Diffusion · Gemma 3" },
  { n: 5, title: "Place it in the video", text: "The ad follows the billboard as the camera moves, and people or buses stay in front of it.", models: "OpenCV · YOLO11" },
  { n: 6, title: "Serve by country", text: "Each viewer gets the version for their country, detected from their connection.", models: "ip-api.com" },
];

const INTEGRATIONS: Integration[] = [
  // external services, called over the internet
  { name: "ip-api.com", by: "IP geolocation API", role: "Detects the viewer's country from their IP, so each viewer gets the local version of the scene.", step: "Serve by country", kind: "api", url: "https://ip-api.com" },
  { name: "OpenStreetMap Nominatim", by: "OpenStreetMap Foundation", role: "Finds local businesses near each placement, the advertisers our outreach contacts.", step: "Advertiser outreach", kind: "api", url: "https://nominatim.openstreetmap.org" },
  { name: "SMTP email", by: "e.g. Gmail", role: "Sends the outreach emails, only after a person approves each one.", step: "Advertiser outreach", kind: "api", url: "https://support.google.com/mail/answer/7126229" },
  { name: "Brave Search API", by: "Brave", role: "Extra web results about a lead (website, contact page) when OpenStreetMap is not enough.", step: "Advertiser outreach", kind: "api", url: "https://brave.com/search/api/", optional: true },
  { name: "Gemini image API", by: "Google", role: "Cloud alternative to Stable Diffusion for extending an ad's background.", step: "Fit the creative", kind: "api", url: "https://ai.google.dev", optional: true },
  // AI models, all running on the laptop's GPU/CPU
  { name: "Gemma 3 (4B) via Ollama", by: "Google · Ollama", role: "Understands the scene, checks brand safety, picks the ad and explains why, describes ad backgrounds and catches fake text in generated images. Also drafts outreach emails.", step: "Steps 2-4, outreach", kind: "local", url: "https://ollama.com/library/gemma3" },
  { name: "OWLv2", by: "Google · Hugging Face", role: "Open-vocabulary detector: finds billboards, posters, screens and bus ads from a text description, no training needed.", step: "Find the ad space", kind: "local", url: "https://huggingface.co/google/owlv2-base-patch16-ensemble" },
  { name: "SAM 2", by: "Meta · Ultralytics", role: "Cuts out the exact outline of each detected surface, so the new ad sits on its corners.", step: "Find the ad space", kind: "local", url: "https://docs.ultralytics.com/models/sam-2/" },
  { name: "YOLO11 segmentation", by: "Ultralytics", role: "Finds people and vehicles in front of the billboard, so they stay in front of the new ad.", step: "Place it in the video", kind: "local", url: "https://docs.ultralytics.com/models/yolo11/" },
  { name: "Stable Diffusion 1.5 Inpainting", by: "Hugging Face Diffusers", role: "Generative expand: paints the missing background around the real ad to fit the billboard's shape.", step: "Fit the creative", kind: "local", url: "https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-inpainting" },
  // video engine
  { name: "OpenCV", by: "Open source", role: "Tracks the billboard frame by frame (optical flow, homography, SIFT) and composites the ad with matching light and grain.", step: "Place it in the video", kind: "engine", url: "https://opencv.org" },
  { name: "FFmpeg", by: "Open source", role: "Encodes the final videos for the web and keeps the original sound.", step: "Place it in the video", kind: "engine", url: "https://ffmpeg.org" },
];

const GROUPS: { kind: Kind; title: string; note: string }[] = [
  { kind: "api", title: "External services", note: "Called over the internet" },
  { kind: "local", title: "AI models", note: "Run on the laptop: private, no per-use cost, work offline" },
  { kind: "engine", title: "Video engine", note: "Open-source libraries" },
];

function IntegrationCard({ it }: { it: Integration }) {
  return (
    <a
      href={it.url}
      target="_blank"
      rel="noreferrer"
      className="group flex flex-col border border-rule bg-card p-5 transition-colors hover:border-ink"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-medium text-ink">{it.name}</p>
          <p className="mt-0.5 text-xs text-muted">{it.by}</p>
        </div>
        <ArrowUpRight size={16} className="shrink-0 text-muted transition-colors group-hover:text-ink" />
      </div>
      <p className="mt-3 flex-1 text-sm leading-relaxed text-ink-2">{it.role}</p>
      <p className="mt-4 flex flex-wrap items-center gap-2 text-xs text-muted">
        <span className="border border-rule px-1.5 py-0.5">{it.step}</span>
        {it.optional && <span className="border border-rule px-1.5 py-0.5">optional</span>}
      </p>
    </a>
  );
}

export default function HowItWorksTab() {
  const counts = {
    api: INTEGRATIONS.filter((i) => i.kind === "api").length,
    local: INTEGRATIONS.filter((i) => i.kind === "local").length,
  };
  return (
    <div>
      <PageHeader
        eyebrow="Under the hood"
        title="How it works"
        lede="From raw footage to a local brand on the billboard in every market. Five AI models do the work, all running on our own laptop, connected to a handful of external services."
        aside={
          <div className="flex gap-10 text-sm">
            <div>
              <p className="text-xs uppercase tracking-[0.14em] text-muted">AI models</p>
              <p className="mt-1 font-serif text-3xl">{counts.local}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.14em] text-muted">External services</p>
              <p className="mt-1 font-serif text-3xl">{counts.api}</p>
            </div>
          </div>
        }
      />

      <Section title="The pipeline">
        <ol className="grid gap-px border border-rule bg-rule sm:grid-cols-2 lg:grid-cols-3">
          {STEPS.map((s) => (
            <li key={s.n} className="bg-card p-5">
              <p className="font-serif text-3xl text-accent">{s.n}</p>
              <p className="mt-2 font-medium">{s.title}</p>
              <p className="mt-1.5 text-sm leading-relaxed text-ink-2">{s.text}</p>
              <p className="mt-3 text-xs uppercase tracking-[0.12em] text-muted">{s.models}</p>
            </li>
          ))}
        </ol>
      </Section>

      <Section title="Powered by" aside="Every service and model in the product, and what it does">
        {GROUPS.map((g) => (
          <div key={g.kind} className="mt-8 first:mt-0">
            <div className="mb-3 flex flex-wrap items-baseline gap-3">
              <h3 className="text-xs font-medium uppercase tracking-[0.18em] text-ink">{g.title}</h3>
              <p className="text-xs text-muted">{g.note}</p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {INTEGRATIONS.filter((i) => i.kind === g.kind).map((it) => (
                <IntegrationCard key={it.name} it={it} />
              ))}
            </div>
          </div>
        ))}
        <p className="mt-8 text-xs text-muted">
          Demo footage: Pexels (free licence). Brand ads are shown for demonstration only, with no affiliation.
        </p>
      </Section>
    </div>
  );
}
