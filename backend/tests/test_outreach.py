"""Outreach tests: fake network, fake Ollama, fake SMTP. Nothing leaves the machine."""
from __future__ import annotations

import email
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings
from backend.geo import GeoResolver
from backend.outreach import mailer as mailer_mod
from backend.outreach.config import OutreachSettings
from backend.outreach.crawl import best_email, extract_emails, parse
from backend.outreach.llm import LLM
from backend.outreach.mailer import looks_personal
from backend.outreach.sources import NOMINATIM, OVERPASS

SITE = "https://baeckerei-mueller.de"
HOME = """<html><head><title>Bäckerei Müller</title>
<meta name="description" content="Familienbäckerei in Berlin-Mitte seit 1962"></head>
<body><script>var x="spam@tracker.io"</script><h1>Frisches Brot</h1>
<a href="/kontakt">Kontakt</a><a href="https://facebook.com/x">fb</a></body></html>"""
KONTAKT = "<html><body><p>Schreiben Sie uns: info [at] baeckerei-mueller.de</p><img src='logo@2x.png'></body></html>"

OVERPASS_DATA = {"elements": [
    {"type": "node", "id": 1, "tags": {"name": "Bäckerei Müller", "shop": "bakery", "website": SITE}},
    {"type": "node", "id": 2, "tags": {"name": "Café Ost", "amenity": "cafe", "email": "hallo@cafe-ost.de"}},
    {"type": "node", "id": 3, "tags": {"name": "Max Imbiss", "amenity": "fast_food",
                                       "email": "max.muster@gmail.com"}},
    {"type": "node", "id": 4, "tags": {"name": "Stille Bar", "amenity": "bar", "website": "https://stille.de"}},
    {"type": "node", "id": 5, "tags": {"name": "Café Ost", "amenity": "cafe"}},           # duplicate name
    {"type": "node", "id": 6, "tags": {"amenity": "cafe", "website": "https://noname.de"}},  # no name
    {"type": "node", "id": 8, "tags": {"name": "BurgerWorld", "amenity": "fast_food", "brand": "BurgerWorld",
                                       "brand:wikidata": "Q1", "email": "info@burgerworld.com"}},  # chain
    {"type": "node", "id": 7, "tags": {"name": "Spielothek Glück", "amenity": "cafe",
                                       "email": "info@spielothek-glueck.de"}},
]}


class FakeHttp:
    def __init__(self, robots_block: bool = False):
        self.calls = []
        self.robots_block = robots_block

    def get_json(self, url, params=None, headers=None):
        self.calls.append(url)
        if url == NOMINATIM:
            return [{"lat": "52.52", "lon": "13.40"}]
        raise AssertionError(url)

    def post_json(self, url, data, timeout=None):
        self.calls.append(url)
        assert url == OVERPASS and "around:" in data["data"]
        return OVERPASS_DATA

    def get_text(self, url, max_bytes=0):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            if self.robots_block:
                return url, "User-agent: *\nDisallow: /"
            raise ConnectionError("no robots")
        pages = {SITE: HOME, f"{SITE}/kontakt": KONTAKT, "https://stille.de": "<html><body>Bar</body></html>"}
        if url in pages:
            return url, pages[url]
        raise ConnectionError(url)


def fake_ollama(prompt: str) -> str:
    if "fit_score" in prompt:
        score = 30 if "Spielothek" in prompt else 85
        return json.dumps({"fit_score": score, "reason": "Local bakery near the filmed street",
                           "category": "food", "summary": "Family bakery", "brand_safe": True})
    return json.dumps({"subject": "Ihre Werbung im Video",
                       "body": "Hallo,\nwir laden Sie ein: {BID_LINK}\nViele Grüße, ProDefenders"})


def osettings(root: Path, **kw) -> OutreachSettings:
    base = dict(db_path=root / "output/outreach.db", outbox_dir=root / "output/outbox",
                public_base_url="http://test", secret_key="s3cret")
    return OutreachSettings(**{**base, **kw})


def make(root: Path, ai=True, http=None, **kw):
    settings = Settings(root=root, geo_enabled=False)
    o = osettings(root, ai_enabled=ai, **kw)
    llm = LLM(o, generate=fake_ollama if ai else None)
    async def no_lookup(ip):
        return None
    app = create_app(settings, GeoResolver(settings, lookup=no_lookup), outreach_settings=o,
                     outreach_http=http or FakeHttp(), outreach_llm=llm)
    return TestClient(app), app


def run_campaign(client, app, **body) -> dict:
    r = client.post("/api/outreach/campaigns", json={"market": "DE", "category": "food", **body})
    assert r.status_code == 202, r.text
    cid = r.json()["id"]
    app.state.outreach._threads[cid].join(timeout=10)
    return client.get(f"/api/outreach/campaigns/{cid}").json()


# ---------- unit ----------
def test_extract_and_pick_email():
    page = parse(HOME + KONTAKT)
    found = extract_emails(page, HOME + KONTAKT)
    assert "info@baeckerei-mueller.de" in found
    assert not any(e.endswith(".png") for e in found)
    assert best_email(["spam@tracker.io", "info@baeckerei-mueller.de"], SITE) == "info@baeckerei-mueller.de"
    assert best_email(["jan@other.de", "info@other.de"], None) == "info@other.de"


def test_looks_personal():
    assert looks_personal("max.muster@gmail.com")
    assert not looks_personal("info@cafe.de") and not looks_personal("kontakt@x.de")


# ---------- campaign ----------
def test_campaign_finds_qualifies_and_drafts(tmp_path):
    client, app = make(tmp_path)
    c = run_campaign(client, app)
    assert c["status"] == "done", c["log"]
    assert c["city"] == "Berlin"
    leads = client.get(f"/api/outreach/campaigns/{c['id']}/leads").json()
    names = {l["name"] for l in leads}
    assert names == {"Bäckerei Müller", "Café Ost", "Max Imbiss", "Stille Bar", "Spielothek Glück"}  # dup, nameless, chain dropped
    bakery = next(l for l in leads if l["name"] == "Bäckerei Müller")
    assert bakery["email"] == "info@baeckerei-mueller.de" and bakery["email_source"] == "website"
    assert bakery["fit_score"] == 85 and bakery["ai"] == "ollama"

    emails = client.get(f"/api/outreach/campaigns/{c['id']}/emails").json()
    assert sorted(e["to_addr"] for e in emails) == ["hallo@cafe-ost.de", "info@baeckerei-mueller.de"]
    e = emails[0]
    assert e["status"] == "draft" and e["language"] == "de" and e["ai"] == "ollama"
    assert "http://test/bid/" in e["body"] and "{BID_LINK}" not in e["body"]
    assert "Unsubscribe: http://test/api/outreach/unsubscribe/" in e["body"]
    log = " ".join(c["log"])
    assert "Max Imbiss" in log and "personal address" in log
    assert "Spielothek Glück: score 30 (ollama), fit score 30 < 50" in log
    assert "Stille Bar: score 85 (ollama), no public email" in log


def test_robots_txt_respected(tmp_path):
    client, app = make(tmp_path, http=FakeHttp(robots_block=True))
    c = run_campaign(client, app)
    leads = client.get(f"/api/outreach/campaigns/{c['id']}/leads").json()
    assert next(l for l in leads if l["name"] == "Bäckerei Müller")["email"] is None


def test_rules_fallback_without_ai(tmp_path):
    client, app = make(tmp_path, ai=False)
    c = run_campaign(client, app, market="RO", city="Cluj-Napoca")
    emails = client.get(f"/api/outreach/campaigns/{c['id']}/emails").json()
    assert emails and all(e["ai"] == "rules" and e["language"] == "ro" for e in emails)
    body = emails[0]["body"]
    assert "Bună ziua" in body and "Licitația pornește de la $40" in body
    assert "10.000 de privitori" in body and "o stradă aglomerată" in body and "busy city" not in body


def test_campaign_validation(tmp_path):
    client, _ = make(tmp_path)
    assert client.post("/api/outreach/campaigns", json={"market": "BR"}).status_code == 400
    assert client.post("/api/outreach/campaigns", json={"market": "DE", "category": "casino"}).status_code == 400


def test_search_failure_marks_campaign_failed(tmp_path):
    class Down(FakeHttp):
        def get_json(self, *a, **k):
            raise ConnectionError("offline")
    client, app = make(tmp_path, http=Down())
    c = run_campaign(client, app)
    assert c["status"] == "failed" and "offline" in c["error"]


# ---------- approval & sending ----------
def test_send_needs_confirm_and_goes_to_outbox_by_default(tmp_path):
    client, app = make(tmp_path)
    cid = run_campaign(client, app)["id"]
    assert client.post(f"/api/outreach/campaigns/{cid}/send", json={}).status_code == 400
    # nothing approved yet -> nothing happens
    r = client.post(f"/api/outreach/campaigns/{cid}/send", json={"confirm": True}).json()
    assert r["results"] == {}
    r = client.post(f"/api/outreach/campaigns/{cid}/send", json={"confirm": True, "approve_all": True}).json()
    assert r["results"] == {"outbox": 2} and r["send_enabled"] is False
    files = sorted((tmp_path / "output/outbox").glob("*.eml"))
    assert len(files) == 2
    msg = email.message_from_bytes(files[0].read_bytes())
    assert msg["List-Unsubscribe"].startswith("<http://test/api/outreach/unsubscribe/")


def test_edit_approve_reject(tmp_path):
    client, app = make(tmp_path)
    cid = run_campaign(client, app)["id"]
    e1, e2 = client.get(f"/api/outreach/campaigns/{cid}/emails").json()
    assert client.patch(f"/api/outreach/emails/{e1['id']}", json={"subject": "Neu"}).json()["subject"] == "Neu"
    assert client.post(f"/api/outreach/emails/{e1['id']}/approve").json()["status"] == "approved"
    assert client.post(f"/api/outreach/emails/{e2['id']}/reject").json()["status"] == "rejected"
    assert client.post(f"/api/outreach/emails/{e2['id']}/approve").status_code == 400


class FakeSMTP:
    sent: list = []

    def __init__(self, host, port, timeout=None):
        self.host = host

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        pass

    def login(self, user, pw):
        pass

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


def test_smtp_send_test_recipient_and_daily_limit(tmp_path, monkeypatch):
    FakeSMTP.sent = []
    monkeypatch.setattr(mailer_mod.smtplib, "SMTP", FakeSMTP)
    client, app = make(tmp_path, send_enabled=True, smtp_host="smtp.test", smtp_from="me@test",
                       test_recipient="demo@me.test", daily_limit=1)
    cid = run_campaign(client, app)["id"]
    r = client.post(f"/api/outreach/campaigns/{cid}/send", json={"confirm": True, "approve_all": True}).json()
    assert r["results"] == {"sent": 1, "approved": 1}          # second one held back by the daily limit
    assert len(FakeSMTP.sent) == 1
    msg = FakeSMTP.sent[0]
    assert msg["To"] == "demo@me.test" and msg["X-Original-To"] in ("hallo@cafe-ost.de", "info@baeckerei-mueller.de")
    held = client.get(f"/api/outreach/campaigns/{cid}/emails?status=approved").json()[0]
    assert "daily limit" in held["error"]


def test_unsubscribe_suppresses(tmp_path):
    client, app = make(tmp_path)
    cid = run_campaign(client, app)["id"]
    e = client.get(f"/api/outreach/campaigns/{cid}/emails").json()[0]
    unsub = e["body"].split("Unsubscribe: http://test")[1].strip()
    page = client.get(unsub)
    assert page.status_code == 200 and e["to_addr"] in page.text
    assert client.get(f"/api/outreach/emails/{e['id']}").json()["status"] == "skipped"
    # a new campaign does not draft to them again
    c2 = run_campaign(client, app)
    to = [x["to_addr"] for x in client.get(f"/api/outreach/campaigns/{c2['id']}/emails").json()]
    assert e["to_addr"] not in to
    assert client.get("/api/outreach/unsubscribe/garbage.token").status_code == 400


# ---------- bidding ----------
def bid_token(client, app) -> str:
    cid = run_campaign(client, app)["id"]
    body = client.get(f"/api/outreach/campaigns/{cid}/emails").json()[0]["body"]
    return body.split("http://test/bid/")[1].split()[0]


def test_bid_page_and_bids(tmp_path):
    client, app = make(tmp_path)
    tok = bid_token(client, app)
    page = client.get(f"/bid/{tok}")
    assert page.status_code == 200 and "Germania" in page.text and "$105.00" in page.text   # DE CPM 10.5 x 10k
    assert client.get(f"/bid/{tok[:-3]}xyz").status_code == 400

    assert client.post("/api/bids", json={"token": tok, "amount_usd": 50}).status_code == 400   # below floor
    first = client.post("/api/bids", json={"token": tok, "amount_usd": 120}).json()
    assert first["leading"] is True and first["rank"] == 1
    second = client.post("/api/bids", json={"token": tok, "amount_usd": 200, "company": "Other GmbH"}).json()
    assert second["leading"] is True
    third = client.post("/api/bids", json={"token": tok, "amount_usd": 150}).json()
    assert third["rank"] == 2 and third["leading"] is False

    pid = first["placement"]["id"]
    assert pid == "demo:s1:DE"
    bids = client.get(f"/api/placements/{pid}/bids").json()
    assert [b["amount_usd"] for b in bids] == [200, 150, 120]
    pl = next(p for p in client.get("/api/placements").json() if p["id"] == pid)
    assert pl["top_bid_usd"] == 200 and pl["bids"] == 3
    assert len(client.get("/api/placements").json()) == 15                     # demo clip x 15 markets


def test_forged_token_rejected(tmp_path):
    client, _ = make(tmp_path)
    from backend.outreach.bids import sign
    forged = sign({"k": "bid", "l": 1, "c": "demo", "m": "DE"}, "wrong-secret")
    assert client.post("/api/bids", json={"token": forged, "amount_usd": 500}).status_code == 400
    unsub_as_bid = sign({"k": "unsub", "e": "a@b.c"}, "s3cret")
    assert client.post("/api/bids", json={"token": unsub_as_bid, "amount_usd": 500}).status_code == 400


def test_status(tmp_path):
    client, _ = make(tmp_path)
    s = client.get("/api/outreach/status").json()
    assert s["send_enabled"] is False and "food" in s["categories"]


# ---------- search resilience ----------
def test_overpass_mirror_fallback_and_cache(tmp_path):
    from backend.outreach.sources import OVERPASS_MIRRORS, Sources

    class Flaky(FakeHttp):
        def post_json(self, url, data, timeout=None):
            self.calls.append(url)
            if url == OVERPASS:
                raise TimeoutError("at capacity")
            return OVERPASS_DATA

    http = Flaky()
    src = Sources(http, cache_dir=tmp_path / "cache")
    first = src.osm("Berlin", "DE", "food", 5)
    assert len(first) == 5 and http.calls.count(OVERPASS_MIRRORS[1]) == 1
    assert src.mirrors[0] == OVERPASS_MIRRORS[1]              # the mirror that answered goes first
    http.calls.clear()
    again = Sources(http, cache_dir=tmp_path / "cache").osm("Berlin", "DE", "food", 5)
    assert [c.name for c in again] == [c.name for c in first]
    assert not [c for c in http.calls if "interpreter" in c]  # served from cache


def test_chains_excluded_unless_asked(tmp_path):
    from backend.outreach.sources import Sources
    names = {c.name for c in Sources(FakeHttp()).osm("Berlin", "DE", "food", 5)}
    assert "BurgerWorld" not in names
    names = {c.name for c in Sources(FakeHttp()).osm("Berlin", "DE", "food", 5, include_chains=True)}
    assert "BurgerWorld" in names


def test_all_overpass_down_is_clear_error(tmp_path):
    from backend.outreach.sources import Sources

    class Down(FakeHttp):
        def post_json(self, url, data, timeout=None):
            raise TimeoutError("busy")

    with pytest.raises(RuntimeError, match="all Overpass servers failed"):
        Sources(Down()).osm("Berlin", "DE", "food", 5)


class _Status(Exception):
    """Like httpx.HTTPStatusError: carries the response with its status code."""
    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.response = type("R", (), {"status_code": code})()


class _Clock:
    def __init__(self):
        self.t, self.sleeps = 0.0, []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def test_busy_servers_are_retried_after_a_pause(tmp_path):
    from backend.outreach.sources import Sources

    class BusyOnce(FakeHttp):
        posts = 0

        def post_json(self, url, data, timeout=None):
            self.posts += 1
            if self.posts <= 3:                   # first round: every mirror says "no free slot"
                raise _Status(429 if "overpass-api" in url else 504)
            return OVERPASS_DATA

    clock = _Clock()
    http = BusyOnce()
    found = Sources(http, sleep=clock.sleep, clock=clock).osm("Berlin", "DE", "food", 5)
    assert len(found) == 5 and len(clock.sleeps) == 1 and http.posts == 4   # one pause, then it answered


def test_busy_retries_stop_at_the_budget():
    from backend.outreach.sources import Sources

    class AlwaysBusy(FakeHttp):
        def post_json(self, url, data, timeout=None):
            raise _Status(429)

    clock = _Clock()
    with pytest.raises(RuntimeError, match=r"HTTP 429.*try again in a minute"):
        Sources(AlwaysBusy(), sleep=clock.sleep, clock=clock, retry_budget_s=60).osm("Berlin", "DE", "food", 5)
    assert clock.t <= 60


def test_stale_cache_used_when_every_server_fails(tmp_path):
    import os
    from backend.outreach.sources import Sources

    cache = tmp_path / "cache"
    first = Sources(FakeHttp(), cache_dir=cache).osm("Berlin", "DE", "food", 5)
    for f in cache.iterdir():                              # make the cached answer 30 days old
        old = f.stat().st_mtime - 30 * 24 * 3600
        os.utime(f, (old, old))

    class Down(FakeHttp):
        def post_json(self, url, data, timeout=None):
            raise TimeoutError("busy")

    again = Sources(Down(), cache_dir=cache).osm("Berlin", "DE", "food", 5)
    assert [c.name for c in again] == [c.name for c in first]


# ---------- campaign lifecycle ----------
def test_same_search_while_running_is_not_started_twice(tmp_path):
    import threading

    gate = threading.Event()

    class Slow(FakeHttp):
        def post_json(self, url, data, timeout=None):
            gate.wait(10)                          # Overpass "still thinking"
            return super().post_json(url, data, timeout)

    client, app = make(tmp_path, http=Slow())
    body = {"market": "DE", "category": "food"}
    first = client.post("/api/outreach/campaigns", json=body).json()
    again = client.post("/api/outreach/campaigns", json=body).json()
    other = client.post("/api/outreach/campaigns", json={**body, "category": "hotel"}).json()
    gate.set()
    for t in app.state.outreach._threads.values():
        t.join(timeout=10)
    assert again["id"] == first["id"]              # a double click returns the running search
    assert other["id"] != first["id"]              # a different search still starts
    assert len(client.get("/api/outreach/campaigns").json()) == 2
    # once it finished, the same search can be run again
    assert client.post("/api/outreach/campaigns", json=body).json()["id"] not in (first["id"], other["id"])


def test_searches_cut_off_by_a_restart_are_marked_failed(tmp_path):
    client, app = make(tmp_path)
    db = app.state.outreach.db
    cid = db.insert("campaigns", {"market": "DE", "city": "Berlin", "category": "food", "clip": "demo",
                                  "query": "{}", "status": "running", "created": 0})
    client2, _ = make(tmp_path)                    # the server starts again on the same database
    c = client2.get(f"/api/outreach/campaigns/{cid}").json()
    assert c["status"] == "failed" and "interrupted" in c["error"]
