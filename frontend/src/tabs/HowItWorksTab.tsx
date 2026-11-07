// "How it works": the integrations first, big and scannable ("Powered by"); details only on click.
// Then the pipeline as one line of six steps. The list mirrors the code: update it when an
// integration is added or removed.
import { useState, type ComponentType } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, ArrowUpRight, Brain, Crosshair, Film, Globe, Mail, MapPin, Scissors, Search, Sparkles, Users } from "lucide-react";
import { PageHeader } from "../components/ui";

type Kind = "local" | "api" | "engine";

interface Integration {
  id: string;
  name: string;
  short: string; // 2-3 words, shown on the card
  by: string;
  role: string; // full sentence, shown on click
  kind: Kind;
  icon: ComponentType<{ size?: number; strokeWidth?: number }>;
  url: string;
}

const INTEGRATIONS: Integration[] = [
  { id: "gemma", name: "Gemma 3", short: "Understands the scene", by: "Google · runs in Ollama", kind: "local", icon: Brain,
    role: "Reads the place, time, weather and mood of the scene, checks it is brand-safe, picks the best ad for each country and explains why. It also describes ad backgrounds, catches fake text in generated images and drafts outreach emails.",
    url: "https://ollama.com/library/gemma3" },
  { id: "sd", name: "Stable Diffusion", short: "Extends the ad", by: "Inpainting · Hugging Face Diffusers", kind: "local", icon: Sparkles,
    role: "Generative expand: keeps the whole real ad and paints the missing background around it, so it fits the billboard's shape without cropping or stretching.",
    url: "https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-inpainting" },
  { id: "owl", name: "OWLv2", short: "Finds billboards", by: "Google · Hugging Face", kind: "local", icon: Search,
    role: "Open-vocabulary detector: finds billboards, posters, screens and bus ads from a plain-text description, with no training.",
    url: "https://huggingface.co/google/owlv2-base-patch16-ensemble" },
  { id: "sam", name: "SAM 2", short: "Cuts the exact shape", by: "Meta · Ultralytics", kind: "local", icon: Scissors,
    role: "Cuts out the exact outline of each detected surface, so the new ad lands precisely on its four corners.",
    url: "https://docs.ultralytics.com/models/sam-2/" },
  { id: "yolo", name: "YOLO11", short: "Keeps people in front", by: "Ultralytics", kind: "local", icon: Users,
    role: "Segments people and vehicles passing in front of the billboard, so they stay in front of the new ad.",
    url: "https://docs.ultralytics.com/models/yolo11/" },
  { id: "ipapi", name: "ip-api", short: "Detects the country", by: "IP geolocation API", kind: "api", icon: Globe,
    role: "Detects the viewer's country from their connection, so each viewer gets the version of the scene made for their market.",
    url: "https://ip-api.com" },
  { id: "osm", name: "OpenStreetMap", short: "Finds advertisers", by: "Nominatim API", kind: "api", icon: MapPin,
    role: "Finds local businesses near each placement: the advertisers our outreach contacts.",
    url: "https://nominatim.openstreetmap.org" },
  { id: "smtp", name: "Email (SMTP)", short: "Contacts advertisers", by: "e.g. Gmail", kind: "api", icon: Mail,
    role: "Sends the outreach emails written by Gemma, only after a person approves each one.",
    url: "https://support.google.com/mail/answer/7126229" },
  { id: "opencv", name: "OpenCV", short: "Tracks the billboard", by: "Open source", kind: "engine", icon: Crosshair,
    role: "Follows the billboard frame by frame as the camera moves (optical flow, homography, SIFT) and blends the ad in with matching light and grain.",
    url: "https://opencv.org" },
  { id: "ffmpeg", name: "FFmpeg", short: "Renders the video", by: "Open source", kind: "engine", icon: Film,
    role: "Encodes the final videos for the web and keeps the original sound.",
    url: "https://ffmpeg.org" },
];

const KIND_LABEL: Record<Kind, string> = { local: "Local AI", api: "External API", engine: "Video engine" };
const KIND_STYLE: Record<Kind, string> = {
  local: "bg-ink text-paper",
  api: "bg-accent text-paper",
  engine: "border border-rule-strong text-ink",
};

const STEPS: { title: string; uses: string[] }[] = [
  { title: "Find the billboard", uses: ["owl", "sam"] },
  { title: "Read the scene", uses: ["gemma"] },
  { title: "Pick the ad", uses: ["gemma"] },
  { title: "Fit the ad", uses: ["sd", "gemma"] },
  { title: "Place in video", uses: ["opencv", "yolo", "ffmpeg"] },
  { title: "Serve by country", uses: ["ipapi"] },
];

const byId = (id: string) => INTEGRATIONS.find((i) => i.id === id)!;

function Tile({ it, active, onClick }: { it: Integration; active: boolean; onClick: () => void }) {
  const Icon = it.icon;
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={`group flex flex-col items-start border bg-card p-5 text-left transition-colors ${
        active ? "border-ink" : "border-rule hover:border-rule-strong"
      }`}
    >
      <span className={`flex size-11 items-center justify-center ${KIND_STYLE[it.kind]}`}>
        <Icon size={22} strokeWidth={1.75} />
      </span>
      <span className="mt-4 break-words font-serif text-lg font-medium leading-tight tracking-tight [overflow-wrap:anywhere] sm:text-2xl">
        {it.name}
      </span>
      <span className="mt-1 text-sm text-ink-2">{it.short}</span>
    </button>
  );
}

export default function HowItWorksTab() {
  const [selected, setSelected] = useState("gemma");
  const sel = byId(selected);
  const local = INTEGRATIONS.filter((i) => i.kind === "local").length;
  const apis = INTEGRATIONS.filter((i) => i.kind === "api").length;

  return (
    <div>
      <PageHeader
        eyebrow="Under the hood"
        title="Powered by"
        lede={`${local} AI models running on our own laptop, ${apis} external services. Click any of them to see what it does.`}
      />

      {/* legend */}
      <div className="-mt-4 mb-5 flex flex-wrap gap-5 text-xs text-muted">
        {(Object.keys(KIND_LABEL) as Kind[]).map((k) => (
          <span key={k} className="inline-flex items-center gap-2">
            <span className={`size-3 ${KIND_STYLE[k]}`} />
            {KIND_LABEL[k]}
          </span>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {INTEGRATIONS.map((it) => (
          <Tile key={it.id} it={it} active={it.id === selected} onClick={() => setSelected(it.id)} />
        ))}
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={sel.id}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          className="mt-3 flex flex-wrap items-start justify-between gap-4 border border-ink bg-card p-5"
        >
          <div className="max-w-3xl">
            <p className="text-xs uppercase tracking-[0.14em] text-muted">
              {KIND_LABEL[sel.kind]} · {sel.by}
            </p>
            <p className="mt-2 text-[15px] leading-relaxed">
              <span className="font-medium">{sel.name}.</span> {sel.role}
            </p>
          </div>
          <a href={sel.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm text-ink-2 hover:text-ink">
            Website <ArrowUpRight size={14} />
          </a>
        </motion.div>
      </AnimatePresence>

      <section className="mt-16">
        <h2 className="mb-5 border-b border-rule pb-3 font-serif text-2xl font-medium tracking-tight">How it works</h2>
        <ol className="flex flex-col gap-3 lg:flex-row lg:items-stretch lg:gap-0">
          {STEPS.map((s, i) => (
            <li key={s.title} className="flex items-stretch lg:flex-1">
              <div className="flex flex-1 flex-col border border-rule bg-card p-4">
                <p className="font-serif text-xl text-accent">{i + 1}</p>
                <p className="mt-1 font-medium leading-snug">{s.title}</p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {s.uses.map((id) => {
                    const it = byId(id);
                    return (
                      <button
                        key={id}
                        onClick={() => setSelected(id)}
                        className={`px-1.5 py-0.5 text-xs ${KIND_STYLE[it.kind]} ${id === selected ? "outline outline-2 outline-offset-1 outline-ink" : ""}`}
                      >
                        {it.name}
                      </button>
                    );
                  })}
                </div>
              </div>
              {i < STEPS.length - 1 && (
                <span className="hidden items-center px-1 text-muted lg:flex" aria-hidden>
                  <ArrowRight size={16} />
                </span>
              )}
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
