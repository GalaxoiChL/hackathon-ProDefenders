"""Campaign = find businesses in a market -> read their sites -> AI qualifies them -> draft emails.

Runs in a background thread; nothing is sent here. Sending is a separate, human-approved step.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict

from .. import regions
from ..config import Settings
from ..store import BadRequest, Store
from .bids import Bids
from .config import MARKET_CITIES, OutreachSettings
from .crawl import Crawler
from .db import DB
from .llm import LLM
from .mailer import Mailer, looks_personal
from .sources import CATEGORY_TAGS, Candidate, Sources


def scene_text(store: Store, clip: str) -> str:
    sc = store.scene_or_none(clip) if clip != "demo" else None
    if sc:
        bits = [sc.location, sc.time_of_day, sc.weather, sc.mood]
        return ", ".join(b for b in bits if b) or "a busy city street"
    return "a busy city street"


class Outreach:
    def __init__(self, settings: Settings, store: Store, os_: OutreachSettings, db: DB,
                 sources: Sources, crawler: Crawler, llm: LLM, bids: Bids, mailer: Mailer):
        self.s, self.store, self.o, self.db = settings, store, os_, db
        self.sources, self.crawler, self.llm, self.bids, self.mailer = sources, crawler, llm, bids, mailer
        self._threads: dict[int, threading.Thread] = {}
        self._create_lock = threading.Lock()
        # searches run in threads of this process: any still "queued"/"running" in the database were cut
        # off when the server stopped, and would otherwise show "Searching" (and be polled) forever
        self.db.execute("UPDATE campaigns SET status='failed', finished=?, error=? "
                        "WHERE status IN ('queued', 'running')",
                        (time.time(), "interrupted: the server stopped before this search finished; start it again"))

    # ---------- AI qualification ----------
    def qualify(self, c: Candidate, wanted: str, market: str, scene: str, site_text: str) -> dict:
        ai = self.llm.json(
            "You qualify local businesses as advertisers for an in-video billboard placement. "
            "Reply ONLY with JSON {\"fit_score\": 0-100, \"reason\": str (one sentence, English), "
            "\"category\": str, \"summary\": str (max 25 words), \"brand_safe\": bool}.\n"
            f"Wanted category: {wanted}. Market: {market}. Video scene: {scene}.\n"
            f"Business: {c.name}; type: {c.category}; website: {c.website}\n"
            f"Site text: {(c.description or '')} {site_text[:1500]}\n"
            "Score high if the business is a real local consumer business matching the category and a "
            "good fit for the scene. brand_safe=false for adult, gambling, weapons, tobacco, political content."
        )
        if ai and isinstance(ai.get("fit_score"), (int, float)):
            score = max(0, min(100, int(ai["fit_score"])))
            if ai.get("brand_safe") is False:
                score = 0
            return {"fit_score": score, "fit_reason": str(ai.get("reason", ""))[:300],
                    "summary": str(ai.get("summary", ""))[:300], "ai": "ollama"}
        # rules fallback: category match, reachable, has something to say about itself
        tags = " ".join(CATEGORY_TAGS.get(wanted, []))
        match = bool(c.category) and c.category in tags
        score = 40 + 30 * match + 15 * bool(c.email) + 15 * bool(c.description or site_text)
        reason = (f"{c.category or 'business'} in the requested '{wanted}' category" if match
                  else f"local {c.category or 'business'} near the filmed area")
        return {"fit_score": score, "fit_reason": reason, "summary": (c.description or "")[:300], "ai": "rules"}

    # ---------- campaign ----------
    def create(self, market: str, category: str, city: str | None, clip: str | None, limit: int,
               min_score: int, include_personal: bool, include_chains: bool = False) -> dict:
        market = market.upper()
        if market not in self.s.markets:
            raise BadRequest(f"{market} is not a demo market ({', '.join(self.s.markets)})")
        if category not in CATEGORY_TAGS and category != "any":
            raise BadRequest(f"category must be one of {sorted(CATEGORY_TAGS) + ['any']}")
        clip = clip or (self.store.list_clips() or ["demo"])[0]
        city = city or MARKET_CITIES.get(market) or regions.label(market)
        query = json.dumps({"limit": limit, "min_score": min_score, "include_personal": include_personal,
                            "include_chains": include_chains})
        with self._create_lock:
            # the same search is already running (double click, a form submitted twice): don't start a
            # second copy, which would hit OpenStreetMap and the AI twice and draft duplicate emails
            same = self.db.one("SELECT id FROM campaigns WHERE market=? AND city=? AND category=? AND clip=? "
                               "AND query=? AND status IN ('queued', 'running') ORDER BY id DESC LIMIT 1",
                               (market, city, category, clip, query))
            if same and (t := self._threads.get(same["id"])) and t.is_alive():
                return self.campaign(same["id"])
            cid = self.db.insert("campaigns", {"market": market, "city": city, "category": category, "clip": clip,
                                               "query": query, "status": "queued", "created": time.time()})
            t = threading.Thread(target=self.run, args=(cid,), daemon=True, name=f"campaign-{cid}")
            self._threads[cid] = t
            t.start()
        return self.campaign(cid)

    def run(self, cid: int) -> None:
        camp = self.db.one("SELECT * FROM campaigns WHERE id=?", (cid,))
        q = json.loads(camp["query"])
        market, city, category, clip = camp["market"], camp["city"], camp["category"], camp["clip"]
        self.db.update("campaigns", cid, status="running")
        try:
            scene = scene_text(self.store, clip)
            self.db.log(cid, f"searching {category} businesses in {city}, {market}")
            cands = self.sources.search(city, market, category, q["limit"], q.get("include_chains", False))
            self.db.log(cid, f"found {len(cands)} candidates")
            drafted = 0
            for c in cands:
                if drafted >= q["limit"]:
                    break
                info = {"text": ""}
                email_source = "osm" if c.email else None
                if c.website:
                    info = self.crawler.enrich(c.website)
                    if info.get("email") and not c.email:
                        c.email, email_source = info["email"], "website"
                    c.description = c.description or info.get("description")
                qual = self.qualify(c, category, market, scene, info.get("text", ""))
                lead_id = self.db.insert("leads", {
                    "campaign_id": cid, "market": market, "city": city, "name": c.name, "category": c.category,
                    "website": c.website, "email": c.email, "email_source": email_source, "phone": c.phone,
                    "address": c.address, "source": c.source, "source_id": c.source_id,
                    "description": qual["summary"] or c.description, "fit_score": qual["fit_score"],
                    "fit_reason": qual["fit_reason"], "ai": qual["ai"], "created": time.time()})
                if not lead_id:
                    continue
                skip = None
                if not c.email:
                    skip = "no public email"
                elif qual["fit_score"] < q["min_score"]:
                    skip = f"fit score {qual['fit_score']} < {q['min_score']}"
                elif looks_personal(c.email) and not q["include_personal"]:
                    skip = "looks like a personal address (GDPR): skipped"
                elif self.db.suppressed(c.email):
                    skip = "unsubscribed earlier"
                self.db.log(cid, f"{c.name}: score {qual['fit_score']} ({qual['ai']})" + (f", {skip}" if skip else ""))
                if skip:
                    continue
                self.draft(cid, lead_id, market, clip, scene)
                drafted += 1
            self.db.update("campaigns", cid, status="done", finished=time.time())
            self.db.log(cid, f"done: {drafted} drafts waiting for approval")
        except Exception as e:
            self.db.update("campaigns", cid, status="failed", error=str(e), finished=time.time())
            self.db.log(cid, f"failed: {e}")

    def draft(self, cid: int, lead_id: int, market: str, clip: str, scene: str) -> int:
        lead = self.db.one("SELECT * FROM leads WHERE id=?", (lead_id,))
        floor = self.bids.floor_usd(market)
        mail = self.mailer.compose(lead, market, scene, floor, self.s.default_views)
        # invite to the movie's most prominent ad place (the detector's most confident surface)
        best = max(self.bids.surfaces(clip), key=lambda sf: sf["confidence"] or 0)["id"]
        body = self.mailer.finalize(mail["body"], lead,
                                    self.bids.bid_link(self.o.public_base_url, lead_id, clip, market, surface=best),
                                    self.bids.unsubscribe_link(self.o.public_base_url, lead["email"]))
        return self.db.insert("emails", {"campaign_id": cid, "lead_id": lead_id, "to_addr": lead["email"],
                                         "subject": mail["subject"], "body": body, "language": mail["language"],
                                         "ai": mail["ai"], "status": "draft", "created": time.time()})

    # ---------- read ----------
    def campaign(self, cid: int) -> dict:
        c = self.db.one("SELECT * FROM campaigns WHERE id=?", (cid,))
        if not c:
            return {}
        c["log"] = json.loads(c["log"] or "[]")
        c["query"] = json.loads(c["query"] or "{}")
        c["leads"] = self.db.one("SELECT COUNT(*) n FROM leads WHERE campaign_id=?", (cid,))["n"]
        c["emails"] = {r["status"]: r["n"] for r in self.db.all(
            "SELECT status, COUNT(*) n FROM emails WHERE campaign_id=? GROUP BY status", (cid,))}
        return c

    # ---------- send ----------
    def send(self, cid: int, approve_all: bool) -> dict:
        if approve_all:
            self.db.execute("UPDATE emails SET status='approved' WHERE campaign_id=? AND status='draft'", (cid,))
        results = {}
        for e in self.db.all("SELECT * FROM emails WHERE campaign_id=? AND status='approved'", (cid,)):
            res = self.mailer.deliver(e, self.bids.unsubscribe_link(self.o.public_base_url, e["to_addr"]))
            self.db.update("emails", e["id"], **res)
            results[res["status"]] = results.get(res["status"], 0) + 1
        return {"campaign": cid, "results": results, "send_enabled": self.o.send_enabled,
                "test_recipient": self.o.test_recipient or None}


def candidate_dict(c: Candidate) -> dict:
    return asdict(c)
