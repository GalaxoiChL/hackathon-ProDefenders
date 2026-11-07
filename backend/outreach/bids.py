"""Ad placements (one per clip x market) and sealed bids on them.

Each invited business gets a signed link (HMAC) that names its placement, so bids can't be
forged for someone else and links can't be guessed. Floor price = market CPM x expected views.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
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
def placement_id(clip: str, market: str) -> str:
    return f"{clip}:{market.upper()}"


class Bids:
    def __init__(self, settings: Settings, store: Store, db: DB, secret: str):
        self.s, self.store, self.db, self.secret = settings, store, db, secret

    def floor_usd(self, market: str) -> float:
        """Minimum bid: market CPM x default views / 1000 (e.g. $10 CPM x 10k views = $100)."""
        return round(regions.cpm_usd(market) * self.s.default_views / 1000, 2)

    def placement(self, clip: str, market: str) -> dict:
        pid = placement_id(clip, market)
        stats = self.db.one("SELECT COUNT(*) n, MAX(amount_usd) top FROM bids WHERE placement=?", (pid,))
        c = regions.get(market) or {}
        return {"id": pid, "clip": clip, "market": market.upper(), "market_name": c.get("name"),
                "flag": c.get("flag"), "floor_usd": self.floor_usd(market),
                "expected_views": self.s.default_views, "cpm_usd": regions.cpm_usd(market),
                "bids": stats["n"], "top_bid_usd": stats["top"]}

    def placements(self) -> list[dict]:
        clips = self.store.list_clips() or ["demo"]
        return [self.placement(c, m) for c in clips for m in self.s.markets]

    def bid_link(self, base_url: str, lead_id: int, clip: str, market: str, days: int = 30) -> str:
        tok = sign({"k": "bid", "l": lead_id, "c": clip, "m": market.upper(),
                    "exp": int(time.time() + days * 86400)}, self.secret)
        return f"{base_url}/bid/{tok}"

    def unsubscribe_link(self, base_url: str, email: str) -> str:
        return f"{base_url}/api/outreach/unsubscribe/{sign({'k': 'unsub', 'e': email.lower()}, self.secret)}"

    def place(self, token: str, amount_usd: float, message: str | None, company: str | None) -> dict:
        data = verify(token, self.secret, "bid")
        clip, market = data["c"], data["m"]
        floor = self.floor_usd(market)
        if amount_usd < floor:
            raise BadRequest(f"minimum bid for this placement is ${floor:.2f}")
        lead = self.db.one("SELECT * FROM leads WHERE id=?", (data["l"],)) or {}
        pid = placement_id(clip, market)
        bid_id = self.db.insert("bids", {
            "placement": pid, "clip": clip, "market": market, "lead_id": data["l"],
            "company": (company or lead.get("name") or "")[:200], "contact_email": lead.get("email"),
            "amount_usd": round(float(amount_usd), 2), "message": (message or "")[:2000],
            "created": time.time()})
        higher = self.db.one("SELECT COUNT(*) n FROM bids WHERE placement=? AND amount_usd>?",
                             (pid, amount_usd))["n"]
        return {"bid_id": bid_id, "placement": self.placement(clip, market), "rank": higher + 1,
                "leading": higher == 0}

    def bids_for(self, pid: str) -> list[dict]:
        return self.db.all("SELECT id, company, contact_email, amount_usd, message, created FROM bids "
                           "WHERE placement=? ORDER BY amount_usd DESC, created ASC", (pid,))
