"""HTTP routes for lead search, outreach emails and bidding."""
from __future__ import annotations

import html
import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ..config import Settings
from ..store import BadRequest, Store
from .bids import Bids, verify
from .config import OutreachSettings
from .crawl import Crawler
from .db import DB
from .http import Http
from .leads import Outreach
from .llm import LLM
from .mailer import Mailer
from .sources import CATEGORY_TAGS, Sources


class CampaignRequest(BaseModel):
    market: str = Field(..., description="one of the demo markets, e.g. DE")
    category: str = Field("food", description=f"{sorted(CATEGORY_TAGS)} or 'any'")
    city: str | None = Field(None, description="default: the market's capital / largest city")
    clip: str | None = Field(None, description="clip whose placement is offered; default: first rendered clip")
    limit: int = Field(10, ge=1, le=50, description="max emails drafted")
    min_score: int = Field(50, ge=0, le=100, description="AI fit score needed to get an email")
    include_personal: bool = Field(False, description="also email name.surname@ addresses (GDPR: off)")
    include_chains: bool = Field(False, description="also big chains (McDonald's...); default: local businesses only")


class EmailEdit(BaseModel):
    subject: str | None = None
    body: str | None = None


class SendRequest(BaseModel):
    confirm: bool = Field(False, description="must be true: you reviewed the drafts")
    approve_all: bool = Field(False, description="approve every remaining draft before sending")


class BidRequest(BaseModel):
    token: str
    amount_usd: float = Field(..., gt=0, le=1_000_000)
    company: str | None = None
    message: str | None = Field(None, max_length=2000)


def build(settings: Settings, store: Store, o: OutreachSettings | None = None,
          http: Http | None = None, llm: LLM | None = None) -> tuple[APIRouter, Outreach]:
    o = o or OutreachSettings.from_env(settings.root)
    db = DB(o.db_path)
    http = http or Http(o)
    llm = llm or LLM(o)
    bids = Bids(settings, store, db, db.secret(o.secret_key))
    svc = Outreach(settings, store, o, db, Sources(http, o.brave_api_key, cache_dir=o.db_path.parent / "outreach_cache"), Crawler(http, o.user_agent),
                   llm, bids, Mailer(o, db, llm))
    r = APIRouter()

    # ---------------- campaigns ----------------
    @r.post("/api/outreach/campaigns", tags=["outreach"], status_code=202,
            summary="Caută firme locale, AI-ul le califică și scrie ciorne de email (nu trimite nimic)")
    def create_campaign(req: CampaignRequest):
        return svc.create(req.market, req.category, req.city, req.clip, req.limit, req.min_score,
                          req.include_personal, req.include_chains)

    @r.get("/api/outreach/campaigns", tags=["outreach"])
    def list_campaigns():
        return [svc.campaign(c["id"]) for c in db.all("SELECT id FROM campaigns ORDER BY id DESC")]

    @r.get("/api/outreach/campaigns/{cid}", tags=["outreach"])
    def get_campaign(cid: int):
        c = svc.campaign(cid)
        if not c:
            raise HTTPException(404, f"no campaign {cid}")
        return c

    @r.get("/api/outreach/campaigns/{cid}/leads", tags=["outreach"], summary="Firmele găsite, cu scorul AI")
    def campaign_leads(cid: int):
        return db.all("SELECT * FROM leads WHERE campaign_id=? ORDER BY fit_score DESC", (cid,))

    @r.get("/api/outreach/campaigns/{cid}/emails", tags=["outreach"])
    def campaign_emails(cid: int, status: str | None = None):
        sql, args = "SELECT * FROM emails WHERE campaign_id=?", [cid]
        if status:
            sql, args = sql + " AND status=?", args + [status]
        return db.all(sql + " ORDER BY id", tuple(args))

    @r.post("/api/outreach/campaigns/{cid}/send", tags=["outreach"],
            summary="Trimite emailurile aprobate (sau le pune în output/outbox/ dacă trimiterea e oprită)")
    def send_campaign(cid: int, req: SendRequest):
        if not req.confirm:
            raise BadRequest("set confirm=true after reviewing the drafts")
        if not svc.campaign(cid):
            raise HTTPException(404, f"no campaign {cid}")
        return svc.send(cid, req.approve_all)

    # ---------------- single emails ----------------
    def _email(eid: int) -> dict:
        e = db.one("SELECT * FROM emails WHERE id=?", (eid,))
        if not e:
            raise HTTPException(404, f"no email {eid}")
        return e

    @r.get("/api/outreach/emails/{eid}", tags=["outreach"])
    def get_email(eid: int):
        return _email(eid)

    @r.patch("/api/outreach/emails/{eid}", tags=["outreach"], summary="Editează ciorna înainte de aprobare")
    def edit_email(eid: int, req: EmailEdit):
        e = _email(eid)
        if e["status"] not in ("draft", "approved"):
            raise BadRequest(f"email is already {e['status']}")
        fields = {k: v for k, v in req.model_dump().items() if v is not None}
        if fields:
            db.update("emails", eid, **fields)
        return _email(eid)

    @r.post("/api/outreach/emails/{eid}/approve", tags=["outreach"])
    def approve_email(eid: int):
        if _email(eid)["status"] != "draft":
            raise BadRequest("only drafts can be approved")
        db.update("emails", eid, status="approved")
        return _email(eid)

    @r.post("/api/outreach/emails/{eid}/reject", tags=["outreach"])
    def reject_email(eid: int):
        if _email(eid)["status"] not in ("draft", "approved"):
            raise BadRequest("only drafts / approved emails can be rejected")
        db.update("emails", eid, status="rejected")
        return _email(eid)

    @r.get("/api/outreach/status", tags=["outreach"], summary="Setările de trimitere active")
    def outreach_status():
        return {"send_enabled": o.send_enabled, "test_recipient": o.test_recipient or None,
                "smtp_configured": bool(o.smtp_host), "daily_limit": o.daily_limit,
                "sent_last_24h": db.sent_today(), "ai_model": o.ollama_model if o.ai_enabled else None,
                "brave_search": bool(o.brave_api_key), "categories": sorted(CATEGORY_TAGS) + ["any"]}

    # ---------------- unsubscribe ----------------
    @r.get("/api/outreach/unsubscribe/{token}", response_class=HTMLResponse, include_in_schema=False)
    def unsubscribe(token: str):
        data = verify(token, bids.secret, "unsub")
        db.suppress(data["e"], "unsubscribe link")
        db.execute("UPDATE emails SET status='skipped', error='recipient unsubscribed' "
                   "WHERE to_addr=? AND status IN ('draft','approved')", (data["e"],))
        return _page("Unsubscribed", f"<p><b>{html.escape(data['e'])}</b> will not receive any more "
                                     "emails from us.</p>")

    # ---------------- movies marketplace (open bidding) ----------------
    from ..marketplace import router as marketplace_router  # noqa: PLC0415
    r.include_router(marketplace_router(settings, store, bids))

    # ---------------- placements & bids ----------------
    @r.get("/api/placements", tags=["bids"], summary="Spațiile publicitare scoase la licitație (clip x suprafață x țară)")
    def placements():
        return bids.placements()

    @r.get("/api/placements/{pid}/bids", tags=["bids"], summary="Ofertele pentru un spațiu, cea mai mare prima")
    def placement_bids(pid: str):
        return bids.bids_for(pid)

    @r.post("/api/bids", tags=["bids"], summary="Plasează o ofertă (din linkul semnat primit pe email)")
    def place_bid(req: BidRequest):
        return bids.place(req.token, req.amount_usd, req.message, req.company)

    @r.get("/bid/{token}", response_class=HTMLResponse, include_in_schema=False)
    def bid_page(token: str):
        try:
            data = verify(token, bids.secret, "bid")
        except BadRequest as e:
            return _page("Invalid link", f"<p>{html.escape(str(e))}</p>", status=400)
        p = bids.placement(data["c"], data["m"], data.get("s", "s1"))
        lead = db.one("SELECT name FROM leads WHERE id=?", (data["l"],)) or {}
        video = None
        try:
            m = store.manifest(data["c"])
            reg = next((x for x in m.regions if x.code.upper() == data["m"]), None)
            video = "/" + reg.video if reg else None
        except Exception:
            pass
        return _page("Place your bid", BID_FORM.format(
            company=html.escape(lead.get("name") or ""), flag=p["flag"] or "",
            market=html.escape(p["market_name"] or p["market"]), clip=html.escape(p["clip"]),
            views=f"{p['expected_views']:,}", floor=f"{p['floor_usd']:.2f}", floor_raw=p["floor_usd"],
            bids=p["bids"], token=json.dumps(token),
            video=f'<video src="{html.escape(video)}" controls muted playsinline></video>' if video else ""))

    return r, svc


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(status_code=status, content=f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
:root{{--bg:#f7f7f5;--fg:#1a1a1a;--card:#fff;--muted:#666;--accent:#c81e23;--line:#e3e3df}}
@media (prefers-color-scheme:dark){{:root{{--bg:#141414;--fg:#eee;--card:#1e1e1e;--muted:#aaa;--line:#333}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}}
main{{max-width:560px;margin:40px auto;padding:0 16px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:24px}}
h1{{font-size:1.4rem;margin:0 0 12px}} .muted{{color:var(--muted)}}
video{{width:100%;border-radius:8px;margin:12px 0}}
label{{display:block;margin:14px 0 4px;font-weight:600}}
input,textarea{{width:100%;box-sizing:border-box;padding:10px;border:1px solid var(--line);border-radius:8px;
background:var(--bg);color:var(--fg);font:inherit}}
button{{margin-top:16px;width:100%;padding:12px;border:0;border-radius:8px;background:var(--accent);
color:#fff;font:600 16px system-ui;cursor:pointer}} #out{{margin-top:14px;font-weight:600}}
</style></head><body><main><div class="card">{body}</div></main></body></html>""")


BID_FORM = """<h1>{flag} Billboard placement, {market}</h1>
<p class="muted">Invitation for <b>{company}</b>. Your ad appears on a real billboard inside the video
<b>{clip}</b>, shown only to viewers in {market}.</p>{video}
<p>Expected views: <b>{views}</b> · Minimum bid: <b>${floor}</b> · Bids so far: <b>{bids}</b></p>
<form id="f"><label for="amount">Your bid (USD)</label>
<input id="amount" type="number" min="{floor_raw}" step="1" required value="{floor_raw}">
<label for="company">Company name</label><input id="company" value="{company}">
<label for="msg">Message (optional)</label><textarea id="msg" rows="3"></textarea>
<button>Place bid</button></form><div id="out" role="status"></div>
<script>
document.getElementById('f').addEventListener('submit', async (ev) => {{
  ev.preventDefault();
  const out = document.getElementById('out');
  const r = await fetch('/api/bids', {{method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{token: {token}, amount_usd: +document.getElementById('amount').value,
      company: document.getElementById('company').value, message: document.getElementById('msg').value}})}});
  const d = await r.json();
  out.textContent = r.ok ? (d.leading ? 'Bid received. You are currently the highest bidder.'
                                      : 'Bid received. Current rank: #' + d.rank + '.')
                         : (d.detail || 'Something went wrong');
}});
</script>"""
