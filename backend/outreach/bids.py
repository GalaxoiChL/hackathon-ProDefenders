"""Ad placements and the bids on them.

A placement is one ad surface (billboard, poster, screen) in one clip, sold in one country:
id "<clip>:<surface>:<COUNTRY>", e.g. "melbourne:s2:DE". Floor price = market CPM x expected views.

Two ways to bid:
  - open marketplace: any business, from the Marketplace page (POST /api/placements/{id}/bids)
  - invitation: a signed link (HMAC) in the outreach email names the placement, so it can't be
    forged for someone else or guessed
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time

from .. import regions
from ..config import Settings
from ..store import BadRequest, Store
from .db import DB


# ---------- signed tokens ----------
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign(payload: dict, secret: str) -> str:
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    mac = hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()[:16]
    return f"{body}.{_b64(mac)}"


def verify(token: str, secret: str, kind: str) -> dict:
    try:
        body, mac = token.split(".", 1)
        good = hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()[:16]
        if not hmac.compare_digest(good, _unb64(mac)):
            raise ValueError
        data = json.loads(_unb64(body))
    except Exception:
        raise BadRequest("invalid or tampered link") from None
    if data.get("k") != kind:
        raise BadRequest("invalid link type")
    if data.get("exp") and data["exp"] < time.time():
        raise BadRequest("this link has expired")
    return data


# ---------- placements ----------
DEFAULT_SURFACE = "s1"
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[a-z]{2,24}$", re.I)


def placement_id(clip: str, market: str, surface: str = DEFAULT_SURFACE) -> str:
    return f"{clip}:{surface}:{market.upper()}"


def parse_placement_id(pid: str) -> tuple[str, str, str]:
    """(clip, surface, MARKET). Old 2-part ids ("clip:RO") mean the clip's first surface."""
    parts = pid.split(":")
    if len(parts) == 2 and all(parts):
        return parts[0], DEFAULT_SURFACE, parts[1].upper()
    if len(parts) == 3 and all(parts):
        return parts[0], parts[1], parts[2].upper()
    raise BadRequest(f"invalid placement id: {pid!r} (expected clip:surface:COUNTRY)")


class Bids:
    def __init__(self, settings: Settings, store: Store, db: DB, secret: str):
        self.s, self.store, self.db, self.secret = settings, store, db, secret
        # bids saved before placements had a surface ("clip:RO") belong to the first surface
        self.db.execute(f"UPDATE bids SET placement = clip || ':{DEFAULT_SURFACE}:' || market "
                        "WHERE length(placement) - length(replace(placement, ':', '')) = 1")

    # ---------- what is for sale ----------
    def surfaces(self, clip: str) -> list[dict]:
        """Ad surfaces of a clip ({id, type, confidence, aspect, corners, frame}); one default if unknown."""
        surf = self.store.surfaces_or_none(clip) if clip != "demo" else None
        if surf and surf.surfaces:
            return [{"id": x.id, "type": x.type, "confidence": x.confidence, "aspect": x.aspect,
                     "corners": x.corners, "frame": x.frame} for x in surf.surfaces]
        return [{"id": DEFAULT_SURFACE, "type": "billboard", "confidence": None, "aspect": None,
                 "corners": None, "frame": 0}]

    def floor_usd(self, market: str) -> float:
        """Minimum bid: market CPM x default views / 1000 (e.g. $10 CPM x 10k views = $100)."""
        return round(regions.cpm_usd(market) * self.s.default_views / 1000, 2)

    def placement(self, clip: str, market: str, surface: str = DEFAULT_SURFACE) -> dict:
        pid = placement_id(clip, market, surface)
        stats = self.db.one("SELECT COUNT(*) n, MAX(amount_usd) top FROM bids WHERE placement=?", (pid,))
        c = regions.get(market) or {}
        return {"id": pid, "clip": clip, "surface_id": surface, "market": market.upper(),
                "market_name": c.get("name"), "flag": c.get("flag"), "floor_usd": self.floor_usd(market),
                "expected_views": self.s.default_views, "cpm_usd": regions.cpm_usd(market),
                "bids": stats["n"], "top_bid_usd": stats["top"]}

    def clips(self) -> list[str]:
        return self.store.list_clips() or ["demo"]

    def placements(self, clip: str | None = None) -> list[dict]:
        return [self.placement(c, m, sf["id"]) for c in ([clip] if clip else self.clips())
                for sf in self.surfaces(c) for m in self.s.markets]

    def check_placement(self, pid: str) -> tuple[str, str, str]:
        """Validate that a placement exists: rendered clip, detected surface, demo market."""
        clip, surface, market = parse_placement_id(pid)
        if clip not in self.clips():
            raise BadRequest(f"unknown movie: {clip!r}")
        if surface not in {sf["id"] for sf in self.surfaces(clip)}:
            raise BadRequest(f"movie {clip!r} has no ad place {surface!r}")
        if market not in self.s.markets:
            raise BadRequest(f"{market} is not one of the markets ({', '.join(self.s.markets)})")
        return clip, surface, market

    # ---------- links (outreach emails) ----------
    def bid_link(self, base_url: str, lead_id: int, clip: str, market: str, days: int = 30,
                 surface: str = DEFAULT_SURFACE) -> str:
        tok = sign({"k": "bid", "l": lead_id, "c": clip, "m": market.upper(), "s": surface,
                    "exp": int(time.time() + days * 86400)}, self.secret)
        return f"{base_url}/bid/{tok}"

    def unsubscribe_link(self, base_url: str, email: str) -> str:
        return f"{base_url}/api/outreach/unsubscribe/{sign({'k': 'unsub', 'e': email.lower()}, self.secret)}"

    # ---------- bidding ----------
    def _ranked(self, clip: str, market: str, surface: str, bid_id: int, amount: float) -> dict:
        pid = placement_id(clip, market, surface)
        higher = self.db.one("SELECT COUNT(*) n FROM bids WHERE placement=? AND amount_usd>?", (pid, amount))["n"]
        return {"bid_id": bid_id, "placement": self.placement(clip, market, surface), "rank": higher + 1,
                "leading": higher == 0}

    def place(self, token: str, amount_usd: float, message: str | None, company: str | None) -> dict:
        """Bid from the signed link in an invitation email."""
        data = verify(token, self.secret, "bid")
        clip, market, surface = data["c"], data["m"], data.get("s", DEFAULT_SURFACE)
        floor = self.floor_usd(market)
        if amount_usd < floor:
            raise BadRequest(f"minimum bid for this placement is ${floor:.2f}")
        lead = self.db.one("SELECT * FROM leads WHERE id=?", (data["l"],)) or {}
        bid_id = self.db.insert("bids", {
            "placement": placement_id(clip, market, surface), "clip": clip, "market": market,
            "lead_id": data["l"], "company": (company or lead.get("name") or "")[:200],
            "contact_email": lead.get("email"), "amount_usd": round(float(amount_usd), 2),
            "message": (message or "")[:2000], "created": time.time()})
        return self._ranked(clip, market, surface, bid_id, amount_usd)

    def place_open(self, pid: str, company: str, email: str, amount_usd: float,
                   message: str | None = None, category: str | None = None) -> dict:
        """Bid from the open marketplace: any business, for one place in one country.
        A new bid from the same business (email) on the same placement replaces its old one."""
        clip, surface, market = self.check_placement(pid)
        company = (company or "").strip()
        email = (email or "").strip().lower()
        if len(company) < 2:
            raise BadRequest("enter your company name")
        if not EMAIL_RE.match(email):
            raise BadRequest("enter a valid contact email")
        floor = self.floor_usd(market)
        if amount_usd < floor:
            raise BadRequest(f"minimum bid for this place in {market} is ${floor:.2f}")
        pid = placement_id(clip, market, surface)
        self.db.execute("DELETE FROM bids WHERE placement=? AND lower(contact_email)=? AND lead_id IS NULL",
                        (pid, email))
        note = (message or "").strip()[:2000]
        if category and category.strip():
            note = f"[{category.strip()[:40]}] {note}".strip()
        bid_id = self.db.insert("bids", {
            "placement": pid, "clip": clip, "market": market, "lead_id": None, "company": company[:200],
            "contact_email": email, "amount_usd": round(float(amount_usd), 2), "message": note,
            "created": time.time()})
        return self._ranked(clip, market, surface, bid_id, amount_usd)

    def bids_for(self, pid: str) -> list[dict]:
        """Public list: company, amount, message, time. Contact emails stay private."""
        clip, surface, market = parse_placement_id(pid)
        return self.db.all("SELECT id, company, amount_usd, message, created FROM bids "
                           "WHERE placement=? ORDER BY amount_usd DESC, created ASC",
                           (placement_id(clip, market, surface),))
