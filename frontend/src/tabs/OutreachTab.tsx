// Aduce advertiseri: AI-ul găsește firme locale, le califică și scrie invitația; nimic nu pleacă fără aprobarea unui om.
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { apiAvailable } from "../data/loadClip";
import { outreach, type Campaign, type Email, type Lead, type Market, type OutreachStatus } from "../data/outreach";
import { regionName } from "../regions";
import { CountryPicker, Dropdown } from "../components/CountryPicker";
import { Button, CountryMark, PageHeader, Section } from "../components/ui";

const POLL_MS = 2500;

const CATEGORY_LABEL: Record<string, string> = {
  food: "Food",
  drinks: "Drinks",
  retail: "Retail",
  beauty: "Beauty",
  fitness: "Fitness",
  hotel: "Hotels",
  any: "Any business",
};
const categoryLabel = (c: string) => CATEGORY_LABEL[c] ?? c;

const running = (c: Campaign) => c.status === "queued" || c.status === "running";

export default function OutreachTab() {
  const [available, setAvailable] = useState<boolean | null>(null);
  useEffect(() => {
    apiAvailable().then(setAvailable);
  }, []);

  return (
    <>
      <PageHeader
        eyebrow="For content owners"
        title="Outreach"
        lede="Find local businesses that fit a scene. The AI reads their website, scores the fit and writes the invitation in their language. Nothing is sent until a person approves it."
        aside={available ? <SendingStatus /> : undefined}
      />
      {available === false && (
        <p className="max-w-xl text-sm leading-relaxed text-ink-2">
          Outreach runs on the ProDefenders API, which is not running. Start it with{" "}
          <code className="font-mono text-xs">uvicorn backend.app:app --port 8000</code> and reload this page.
        </p>
      )}
      {available && <Workspace />}
    </>
  );
}

function SendingStatus() {
  const [s, setS] = useState<OutreachStatus | null>(null);
  useEffect(() => {
    outreach.status().then(setS, () => {});
  }, []);
  if (!s) return null;
  return (
    <dl className="grid grid-cols-2 gap-x-8 gap-y-3 text-sm">
      <div>
        <dt className="text-xs text-muted">Sending</dt>
        <dd className={s.send_enabled ? "text-accent" : ""}>{s.send_enabled ? (s.test_recipient ? "On, to a test inbox" : "On") : "Off: outbox only"}</dd>
      </div>
      <div>
        <dt className="text-xs text-muted">AI</dt>
        <dd>{s.ai_model ?? "Rule-based"}</dd>
      </div>
      <div>
        <dt className="text-xs text-muted">Sent today</dt>
        <dd className="tabular-nums">
          {s.sent_last_24h} / {s.daily_limit}
        </dd>
      </div>
      {s.test_recipient && (
        <div>
          <dt className="text-xs text-muted">Test inbox</dt>
          <dd className="truncate">{s.test_recipient}</dd>
        </div>
      )}
    </dl>
  );
}

function Workspace() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const refresh = useCallback(() => outreach.campaigns().then(setCampaigns, () => {}), []);
  useEffect(() => {
    refresh();
  }, [refresh]);
  // cât timp rulează o căutare, reîncărcăm lista ca să se vadă progresul
  const busy = campaigns.some(running);
  useEffect(() => {
    if (!busy) return;
    const t = window.setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [busy, refresh]);

  const selected = campaigns.find((c) => c.id === selectedId) ?? campaigns[0];

  return (
    <>
      <NewSearch
        onStarted={(c) => {
          setCampaigns((list) => [c, ...list.filter((x) => x.id !== c.id)]);
          setSelectedId(c.id);
        }}
      />
      <Section title="Searches" aside={campaigns.length ? `${campaigns.length} so far` : undefined}>
        {campaigns.length === 0 ? (
          <p className="text-sm text-muted">No searches yet. Start one above.</p>
        ) : (
          <div className="grid gap-10 lg:grid-cols-[300px_minmax(0,1fr)]">
            <ul>
              {campaigns.map((c) => (
                <li key={c.id}>
                  <button
                    onClick={() => setSelectedId(c.id)}
                    className={`relative w-full border-b border-rule py-3 pr-2 pl-3 text-left transition-colors ${c.id === selected?.id ? "bg-card" : "hover:bg-card/60"}`}
                  >
                    {c.id === selected?.id && <motion.span layoutId="campaign-active" className="absolute inset-y-0 left-0 w-[2px] bg-ink" />}
                    <span className="flex items-baseline justify-between gap-3">
                      <span className="font-serif text-base">
                        {categoryLabel(c.category)} in {c.city ?? regionName(c.market)}
                      </span>
                      <CampaignState c={c} />
                    </span>
                    <span className="mt-1 flex items-center gap-3 text-xs text-muted">
                      <CountryMark code={c.market} muted />
                      <span>
                        {c.leads} found · {Object.values(c.emails).reduce((a, b) => a + b, 0)} emails
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            <AnimatePresence mode="wait">
              {selected && (
                <motion.div key={selected.id} initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
                  <CampaignDetail campaign={selected} onChanged={refresh} />
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}
      </Section>
    </>
  );
}

function CampaignState({ c }: { c: Campaign }) {
  if (running(c))
    return (
      <span className="inline-flex shrink-0 items-center gap-1.5 text-xs">
        <span className="size-1.5 animate-pulse rounded-full bg-positive" />
        {c.status === "queued" ? "Queued" : "Searching"}
      </span>
    );
  return <span className={`shrink-0 text-xs ${c.status === "failed" ? "text-accent" : "text-muted"}`}>{c.status === "failed" ? "Failed" : "Done"}</span>;
}

function NewSearch({ onStarted }: { onStarted: (c: Campaign) => void }) {
  const [markets, setMarkets] = useState<Market[]>([]);
  const [categories, setCategories] = useState<string[]>(["food"]);
  const [market, setMarket] = useState("RO");
  const [category, setCategory] = useState("food");
  const [city, setCity] = useState("");
  const [limit, setLimit] = useState(5);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    outreach.markets().then(setMarkets, () => {});
    outreach.status().then((s) => s.categories.length && setCategories(s.categories), () => {});
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      onStarted(await outreach.start({ market, category, city: city.trim() || undefined, limit }));
      setCity("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={submit} className="border border-rule bg-card p-6">
      <p className="font-serif text-xl">Find businesses</p>
      <p className="mt-1 text-sm text-muted">Searches OpenStreetMap for local businesses (big chains are left out) and drafts an email for each good fit.</p>
      <div className="mt-5 flex flex-wrap items-end gap-4">
        <div className="text-sm">
          <span className="mb-1.5 block text-xs uppercase tracking-[0.14em] text-muted">Market</span>
          <CountryPicker
            value={market}
            onChange={setMarket}
            options={(markets.length ? markets : [{ code: "RO" }]).map((m) => ({ code: m.code, detail: m.brand ?? undefined }))}
          />
        </div>
        <div className="text-sm">
          <span className="mb-1.5 block text-xs uppercase tracking-[0.14em] text-muted">Category</span>
          <Dropdown
            label="Category"
            className="min-w-44"
            value={category}
            onChange={setCategory}
            options={categories.map((c) => ({ value: c, label: categoryLabel(c) }))}
          />
        </div>
        <label className="text-sm">
          <span className="mb-1.5 block text-xs uppercase tracking-[0.14em] text-muted">City</span>
          <input
            value={city}
            onChange={(e) => setCity(e.target.value)}
            placeholder="Largest city"
            className="w-44 border border-rule-strong bg-card px-3 py-2 outline-none focus:border-ink"
          />
        </label>
        <label className="text-sm">
          <span className="mb-1.5 block text-xs uppercase tracking-[0.14em] text-muted">Max emails</span>
          <input
            type="number"
            min={1}
            max={50}
            value={limit}
            onChange={(e) => setLimit(Math.max(1, Math.min(50, Number(e.target.value) || 1)))}
            className="w-24 border border-rule-strong bg-card px-3 py-2 tabular-nums outline-none focus:border-ink"
          />
        </label>
        <Button type="submit" disabled={submitting}>
          {submitting ? "Starting…" : "Find businesses"}
        </Button>
      </div>
      {error && <p className="mt-3 text-sm text-accent">{error}</p>}
    </form>
  );
}

function CampaignDetail({ campaign, onChanged }: { campaign: Campaign; onChanged: () => void }) {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [emails, setEmails] = useState<Email[]>([]);

  const load = useCallback(() => {
    outreach.leads(campaign.id).then(setLeads, () => {});
    outreach.emails(campaign.id).then(setEmails, () => {});
  }, [campaign.id]);
  // reîncărcăm la fiecare schimbare a campaniei (lista o reîncarcă des cât timp rulează)
  useEffect(load, [load, campaign.leads, campaign.status, campaign.emails]);

  const updateEmail = (e: Email) => {
    setEmails((list) => list.map((x) => (x.id === e.id ? e : x)));
    onChanged();
  };

  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 className="font-serif text-2xl">
          {categoryLabel(campaign.category)} in {campaign.city ?? regionName(campaign.market)}
        </h3>
        <CampaignState c={campaign} />
      </div>
      <p className="mt-1 text-sm text-muted">
        {regionName(campaign.market)} · placement in <span className="capitalize">{campaign.clip}</span>
      </p>
      {campaign.error && <p className="mt-3 text-sm text-accent">{campaign.error}</p>}

      {campaign.log.length > 0 && (
        <details className="mt-4" open={running(campaign)}>
          <summary className="cursor-pointer text-xs uppercase tracking-[0.14em] text-muted">Activity</summary>
          <ol className="mt-2 max-h-40 overflow-y-auto border-l border-rule pl-3 font-mono text-[11px] leading-relaxed text-ink-2">
            {campaign.log.slice(-12).map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ol>
        </details>
      )}

      <h4 className="mt-8 border-b border-ink pb-2 text-xs uppercase tracking-[0.14em] text-muted">Businesses found · {leads.length}</h4>
      {leads.length === 0 ? (
        <p className="py-4 text-sm text-muted">{running(campaign) ? "Searching…" : "No businesses found."}</p>
      ) : (
        <ul>
          {leads.map((l) => (
            <LeadRow key={l.id} lead={l} />
          ))}
        </ul>
      )}

      <EmailList campaign={campaign} emails={emails} onUpdate={updateEmail} onSent={load} />
    </div>
  );
}

function LeadRow({ lead }: { lead: Lead }) {
  return (
    <li className="grid grid-cols-[minmax(0,1fr)_88px] gap-x-4 border-b border-rule py-3 text-sm">
      <div className="min-w-0">
        <p className="font-medium">{lead.name}</p>
        <p className="mt-0.5 text-xs text-muted">
          {[lead.category, lead.email ?? "no public email"].filter(Boolean).join(" · ")}
          {lead.website && (
            <>
              {" · "}
              <a href={lead.website} target="_blank" rel="noopener noreferrer" className="underline decoration-rule-strong underline-offset-2 hover:decoration-ink">
                website
              </a>
            </>
          )}
        </p>
        {lead.fit_reason && <p className="mt-1 text-xs text-ink-2">{lead.fit_reason}</p>}
      </div>
      <div className="text-right">
        <p className="font-serif text-lg tabular-nums">{lead.fit_score}</p>
        <span className="mt-1 block h-1 bg-rule">
          <motion.span
            className="block h-full bg-ink"
            initial={{ width: 0 }}
            animate={{ width: `${lead.fit_score}%` }}
            transition={{ duration: 0.6, ease: [0.2, 0.7, 0.2, 1] }}
          />
        </span>
        <p className="mt-1 text-[10px] text-muted">{lead.ai === "ollama" ? "AI score" : "rule score"}</p>
      </div>
    </li>
  );
}

const EMAIL_STATE: Record<string, { label: string; cls: string }> = {
  draft: { label: "Draft", cls: "text-muted" },
  approved: { label: "Approved", cls: "text-positive" },
  rejected: { label: "Rejected", cls: "text-accent" },
  outbox: { label: "In outbox", cls: "text-ink" },
  sent: { label: "Sent", cls: "text-positive" },
  failed: { label: "Failed", cls: "text-accent" },
  skipped: { label: "Skipped", cls: "text-muted" },
};

function EmailList({
  campaign,
  emails,
  onUpdate,
  onSent,
}: {
  campaign: Campaign;
  emails: Email[];
  onUpdate: (e: Email) => void;
  onSent: () => void;
}) {
  const [status, setStatus] = useState<OutreachStatus | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    outreach.status().then(setStatus, () => {});
  }, []);

  const approved = emails.filter((e) => e.status === "approved").length;
  const where = !status?.send_enabled
    ? "Sending is off, so they will be saved as files in output/outbox/ and nothing leaves this computer."
    : status.test_recipient
      ? `They will all go to the test inbox ${status.test_recipient}, not to the businesses.`
      : "They will go to the businesses' real addresses.";

  const send = async () => {
    setError(null);
    try {
      const r = await outreach.send(campaign.id);
      setResult(
        Object.entries(r.results)
          .map(([k, n]) => `${n} ${EMAIL_STATE[k]?.label.toLowerCase() ?? k}`)
          .join(", ") || "Nothing to send.",
      );
      onSent();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setConfirming(false);
    }
  };

  return (
    <div className="mt-10">
      <h4 className="border-b border-ink pb-2 text-xs uppercase tracking-[0.14em] text-muted">Invitation emails · {emails.length}</h4>
      {emails.length === 0 ? (
        <p className="py-4 text-sm text-muted">
          {running(campaign) ? "Drafts appear here as the AI writes them." : "No drafts: no business had a public email and a high enough score."}
        </p>
      ) : (
        <ul>
          {emails.map((e) => (
            <EmailCard key={e.id} email={e} onUpdate={onUpdate} />
          ))}
        </ul>
      )}

      {emails.length > 0 && (
        <div className="mt-6 border border-rule bg-card p-5">
          <AnimatePresence mode="wait">
            {confirming ? (
              <motion.div key="confirm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <p className="text-sm">
                  Send {approved} approved email{approved === 1 ? "" : "s"}? {where}
                </p>
                <div className="mt-4 flex gap-3">
                  <Button onClick={send}>Yes, send</Button>
                  <Button variant="secondary" onClick={() => setConfirming(false)}>
                    Cancel
                  </Button>
                </div>
              </motion.div>
            ) : (
              <motion.div key="idle" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex flex-wrap items-center justify-between gap-4">
                <p className="text-sm text-ink-2">
                  {approved} approved · only approved emails are sent
                </p>
                <Button onClick={() => setConfirming(true)} disabled={approved === 0}>
                  Send approved
                </Button>
              </motion.div>
            )}
          </AnimatePresence>
          {result && <p className="mt-3 text-sm text-positive">{result}</p>}
          {error && <p className="mt-3 text-sm text-accent">{error}</p>}
        </div>
      )}
    </div>
  );
}

function EmailCard({ email, onUpdate }: { email: Email; onUpdate: (e: Email) => void }) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [subject, setSubject] = useState(email.subject);
  const [body, setBody] = useState(email.body);
  const [error, setError] = useState<string | null>(null);
  const editable = email.status === "draft" || email.status === "approved";
  const state = EMAIL_STATE[email.status] ?? { label: email.status, cls: "text-muted" };

  const act = async (fn: () => Promise<Email>) => {
    setError(null);
    try {
      onUpdate(await fn());
      setEditing(false);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <li className="border-b border-rule py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <button onClick={() => setOpen((o) => !o)} className="min-w-0 flex-1 text-left">
          <p className="truncate text-sm font-medium">{email.subject}</p>
          <p className="mt-0.5 truncate text-xs text-muted">
            To {email.to_addr}
            {email.language ? ` · ${email.language.toUpperCase()}` : ""}
          </p>
        </button>
        <span className={`text-xs ${state.cls}`}>{state.label}</span>
      </div>
      {email.error && <p className="mt-1 text-xs text-accent">{email.error}</p>}

      <AnimatePresence initial={false}>
        {(open || editing) && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.22 }} className="overflow-hidden">
            {editing ? (
              <div className="mt-3 space-y-2">
                <input
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  aria-label="Subject"
                  className="block w-full border border-rule-strong bg-card px-3 py-2 text-sm outline-none focus:border-ink"
                />
                <textarea
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  rows={10}
                  aria-label="Email text"
                  className="block w-full border border-rule-strong bg-card px-3 py-2 font-mono text-xs leading-relaxed outline-none focus:border-ink"
                />
              </div>
            ) : (
              <pre className="mt-3 max-h-72 overflow-y-auto whitespace-pre-wrap border-l-2 border-rule pl-4 font-sans text-sm leading-relaxed text-ink-2">{email.body}</pre>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {editable && (
        <div className="mt-3 flex flex-wrap gap-4 text-sm">
          {editing ? (
            <>
              <Button variant="link" onClick={() => act(() => outreach.edit(email.id, { subject, body }))}>
                Save
              </Button>
              <Button
                variant="link"
                className="text-muted"
                onClick={() => {
                  setEditing(false);
                  setSubject(email.subject);
                  setBody(email.body);
                }}
              >
                Cancel
              </Button>
            </>
          ) : (
            <>
              {email.status === "draft" && (
                <Button variant="link" onClick={() => act(() => outreach.approve(email.id))}>
                  Approve
                </Button>
              )}
              <Button variant="link" onClick={() => setEditing(true)}>
                Edit
              </Button>
              <Button variant="link" className="text-accent" onClick={() => act(() => outreach.reject(email.id))}>
                Reject
              </Button>
            </>
          )}
        </div>
      )}
      {error && <p className="mt-2 text-xs text-accent">{error}</p>}
    </li>
  );
}
