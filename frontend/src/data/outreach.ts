// Prospectarea advertiserilor din backend (backend/outreach/routes.py): căutare de firme, ciorne de email, trimitere.
import { assetUrl } from "./loadClip";

export interface OutreachStatus {
  send_enabled: boolean;
  test_recipient: string | null;
  smtp_configured: boolean;
  daily_limit: number;
  sent_last_24h: number;
  ai_model: string | null;
  brave_search: boolean;
  categories: string[];
}

export interface Campaign {
  id: number;
  market: string;
  city: string | null;
  category: string;
  clip: string;
  status: "queued" | "running" | "done" | "failed";
  error: string | null;
  created: number;
  finished: number | null;
  /** „HH:MM:SS mesaj” */
  log: string[];
  leads: number;
  /** câte emailuri sunt în fiecare stare */
  emails: Record<string, number>;
}

export interface Lead {
  id: number;
  name: string;
  category: string | null;
  city: string | null;
  website: string | null;
  email: string | null;
  description: string | null;
  fit_score: number;
  fit_reason: string | null;
  /** "ollama" sau "rules" */
  ai: string;
}

export type EmailStatus = "draft" | "approved" | "rejected" | "outbox" | "sent" | "failed" | "skipped";

export interface Email {
  id: number;
  lead_id: number;
  to_addr: string;
  subject: string;
  body: string;
  language: string | null;
  status: EmailStatus;
  error: string | null;
}

export interface Market {
  code: string;
  name?: string;
  brand?: string | null;
}

/** Cere JSON și aruncă o eroare cu mesajul din backend („detail”) dacă răspunsul nu e OK. */
async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(assetUrl(path), {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    cache: "no-store",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data as { detail?: string }).detail ?? `Request failed (${res.status})`);
  return data as T;
}

const json = (method: string, body?: unknown): RequestInit => ({ method, body: body === undefined ? undefined : JSON.stringify(body) });

export const outreach = {
  status: () => call<OutreachStatus>("api/outreach/status"),
  markets: () => call<Market[]>("api/markets"),
  campaigns: () => call<Campaign[]>("api/outreach/campaigns"),
  leads: (cid: number) => call<Lead[]>(`api/outreach/campaigns/${cid}/leads`),
  emails: (cid: number) => call<Email[]>(`api/outreach/campaigns/${cid}/emails`),
  start: (req: { market: string; category: string; city?: string; limit: number }) =>
    call<Campaign>("api/outreach/campaigns", json("POST", req)),
  edit: (eid: number, fields: { subject?: string; body?: string }) => call<Email>(`api/outreach/emails/${eid}`, json("PATCH", fields)),
  approve: (eid: number) => call<Email>(`api/outreach/emails/${eid}/approve`, json("POST")),
  reject: (eid: number) => call<Email>(`api/outreach/emails/${eid}/reject`, json("POST")),
  send: (cid: number) =>
    call<{ results: Record<string, number>; send_enabled: boolean; test_recipient: string | null }>(
      `api/outreach/campaigns/${cid}/send`,
      json("POST", { confirm: true }),
    ),
};
