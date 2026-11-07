"""Movies marketplace: movies table, ad places per movie, open bids per place and country."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings
from backend.geo import GeoResolver
from backend.outreach.config import OutreachSettings
from backend.outreach.llm import LLM

SURFACES = {"clip": "street", "surfaces": [
    {"id": "s1", "type": "poster", "frame": 0, "corners": [[40, 20], [80, 22], [80, 70], [40, 68]],
     "aspect": 0.8, "confidence": 0.5},
    {"id": "s2", "type": "billboard", "frame": 0, "corners": [[100, 10], [150, 10], [150, 40], [100, 40]],
     "aspect": 1.6, "confidence": 0.9},
]}


def write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8") if isinstance(data, (dict, list)) else path.write_bytes(data)
    return path


def tiny_video(path: Path, frames: int = 30) -> None:
    cv2 = pytest.importorskip("cv2")
    import numpy as np
    path.parent.mkdir(parents=True, exist_ok=True)
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (160, 90))
    for i in range(frames):
        f = np.full((90, 160, 3), 90, np.uint8)
        f[20:70, 40:80] = (40, 40, 220)
        vw.write(f)
    vw.release()


def make(root: Path) -> TestClient:
    settings = Settings(root=root, geo_enabled=False)
    o = OutreachSettings(db_path=root / "output/outreach.db", outbox_dir=root / "output/outbox",
                         public_base_url="http://test", secret_key="s3cret", ai_enabled=False)

    async def no_lookup(ip):
        return None
    app = create_app(settings, GeoResolver(settings, lookup=no_lookup), outreach_settings=o,
                     outreach_llm=LLM(o))
    return TestClient(app)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    write(tmp_path / "output/street.manifest.json", {
        "clip": "street", "regions": [{"code": "RO", "video": "output/street_ro.mp4"}]})
    write(tmp_path / "output/street_ro.mp4", b"x")
    write(tmp_path / "output/street.surfaces.json", SURFACES)
    write(tmp_path / "output/street.scene.json", {"clip": "street", "location": "urban street",
                                                 "time_of_day": "day", "brand_safety": {"safe": True}})
    return tmp_path


def test_movies_table(root):
    movies = make(root).get("/api/movies").json()
    assert [m["clip"] for m in movies] == ["street"]
    m = movies[0]
    assert m["title"] == "Street" and m["places"] == 2 and m["placements"] == 2 * 15
    assert m["bids"] == 0 and m["top_bid_usd"] is None and m["min_floor_usd"] > 0
    assert m["scene"]["location"] == "urban street"
    assert m["thumbnail_url"] == "/api/movies/street/thumbnail.jpg"


def test_movie_detail_lists_every_place_per_country(root):
    d = make(root).get("/api/movies/street").json()
    assert [p["id"] for p in d["places"]] == ["s1", "s2"]
    s2 = d["places"][1]
    assert s2["type"] == "billboard" and s2["label"] == "Ad place 2"
    assert s2["image_url"] == "/api/movies/street/places/s2.jpg"
    ids = [o["id"] for o in s2["offers"]]
    assert len(ids) == 15 and "street:s2:DE" in ids
    de = next(o for o in s2["offers"] if o["market"] == "DE")
    assert de["floor_usd"] == 105.0 and de["surface_id"] == "s2" and de["market_name"] == "Germania"


def test_unknown_movie(root):
    c = make(root)
    assert c.get("/api/movies/nope").status_code == 404
    assert c.get("/api/movies/street/places/..%2Fx.jpg").status_code == 404


def test_open_bid_flow(root):
    c = make(root)
    url = "/api/placements/street:s2:DE/bids"
    ok = {"company": "Brezelhaus", "email": "Info@Brezelhaus.de", "amount_usd": 150, "category": "food",
          "message": "Fresh pretzels"}
    r = c.post(url, json=ok).json()
    assert r["leading"] and r["rank"] == 1 and r["placement"]["id"] == "street:s2:DE"
    # someone else outbids, then the first business raises its own bid: it replaces the old one
    assert c.post(url, json={**ok, "company": "Wiener Kipferl", "email": "hi@kipferl.at", "amount_usd": 200}
                  ).json()["leading"]
    again = c.post(url, json={**ok, "email": "info@brezelhaus.de", "amount_usd": 260}).json()
    assert again["leading"] and again["placement"]["bids"] == 2
    bids = c.get("/api/placements/street:s2:DE/bids").json()
    assert [(b["company"], b["amount_usd"]) for b in bids] == [("Brezelhaus", 260), ("Wiener Kipferl", 200)]
    assert all("contact_email" not in b for b in bids)                   # emails stay private
    assert bids[0]["message"] == "[food] Fresh pretzels"
    # the other place and other countries are separate auctions
    assert c.get("/api/placements/street:s1:DE/bids").json() == []
    movie = c.get("/api/movies").json()[0]
    assert movie["bids"] == 2 and movie["top_bid_usd"] == 260
    place = next(p for p in c.get("/api/movies/street").json()["places"] if p["id"] == "s2")
    assert place["bids"] == 2 and place["top_bid_usd"] == 260


@pytest.mark.parametrize("pid,body,msg", [
    ("street:s2:DE", {"amount_usd": 50}, "minimum bid"),
    ("street:s2:DE", {"email": "not-an-email"}, "valid contact email"),
    ("street:s9:DE", {}, "no ad place"),
    ("street:s2:BR", {}, "not one of the markets"),
    ("other:s1:DE", {}, "unknown movie"),
    ("garbage", {}, "invalid placement id"),
])
def test_open_bid_validation(root, pid, body, msg):
    base = {"company": "Brezelhaus", "email": "info@brezelhaus.de", "amount_usd": 150}
    r = make(root).post(f"/api/placements/{pid}/bids", json={**base, **body})
    assert r.status_code == 400 and msg in r.json()["detail"]


def test_old_two_part_ids_still_work_and_migrate(root):
    c = make(root)
    c.post("/api/placements/street:s1:RO/bids", json={"company": "Pizza X", "email": "a@pizza.ro", "amount_usd": 60})
    db = sqlite3.connect(root / "output/outreach.db")
    db.execute("INSERT INTO bids (placement, clip, market, company, amount_usd, created) "
               "VALUES ('street:RO', 'street', 'RO', 'Old Bidder', 70, 0)")
    db.commit()
    db.close()
    c2 = make(root)                                                     # restart: migration runs
    names = [b["company"] for b in c2.get("/api/placements/street:RO/bids").json()]
    assert names == ["Old Bidder", "Pizza X"]                           # old id == first place


def test_images_from_video(root):
    tiny_video(root / "output/street_original.mp4")
    c = make(root)
    t = c.get("/api/movies/street/thumbnail.jpg")
    assert t.status_code == 200 and t.headers["content-type"] == "image/jpeg" and t.content[:2] == b"\xff\xd8"
    p = c.get("/api/movies/street/places/s1.jpg")
    assert p.status_code == 200 and p.content[:2] == b"\xff\xd8"
    assert (root / "output/thumbs/street__s1.jpg").is_file()             # cached
    d = c.get("/api/movies/street").json()
    assert d["duration_s"] == 3.0 and d["video_url"] == "/output/street_original.mp4"
    assert d["places"][0]["frame_share_pct"] == pytest.approx(13.6, abs=1)


def test_no_video_no_image(root):
    assert make(root).get("/api/movies/street/thumbnail.jpg").status_code == 404
