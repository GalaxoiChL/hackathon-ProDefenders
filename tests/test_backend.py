"""API tests on a temporary repo layout (no real videos, no network)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings
from backend.geo import GeoResolver
from backend.jobs import JobRunner
from backend.models import JobRequest
from backend.regions import region_for_country
from backend.stats import polygon_area
from backend.store import Store

CORNERS = [[1071, 356], [1221, 369], [1223, 565], [1071, 559]]


def write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, (dict, list)):
        path.write_text(json.dumps(data), encoding="utf-8")
    else:
        path.write_bytes(data)
    return path


@pytest.fixture
def root(tmp_path: Path) -> Path:
    out = tmp_path / "output"
    for name in ("melbourne_ro.mp4", "melbourne_us.mp4", "melbourne_jp.mp4", "melbourne_ai_view.mp4",
                 "melbourne_ro.tmp.mp4", "compare.mp4"):
        write(out / name, b"0123456789" * 10)
    write(tmp_path / "assets/clips/melbourne.corners.json", {"frame": 0, "corners": CORNERS})
    return tmp_path


def make_client(root: Path, lookup=None) -> TestClient:
    settings = Settings(root=root, geo_enabled=lookup is not None)
    async def default_lookup(ip):
        return None
    geo = GeoResolver(settings, lookup=lookup or default_lookup)
    return TestClient(create_app(settings, geo))


@pytest.fixture
def client(root: Path) -> TestClient:
    return make_client(root)


# ---------- pure functions ----------
def test_region_for_country():
    avail = ["RO", "US", "JP"]
    assert region_for_country("us", avail, "RO") == "US"
    assert region_for_country("MD", avail, "RO") == "RO"      # nearest market
    assert region_for_country("CA", avail, "RO") == "US"
    assert region_for_country("FR", avail, "RO") == "RO"      # default
    assert region_for_country("FR", ["JP"], "RO") == "JP"     # default not rendered
    assert region_for_country("RO", [], "RO") is None


def test_polygon_area():
    assert polygon_area([[0, 0], [10, 0], [10, 5], [0, 5]]) == 50


# ---------- meta ----------
def test_health(client):
    r = client.get("/api/health").json()
    assert r["status"] == "ok"
    assert r["clips"] == ["melbourne"]
    assert r["ads_source"] == "sample"


def test_root_without_frontend(client):
    assert client.get("/").json()["docs"] == "/docs"


def test_frontend_served_when_present(root):
    write(root / "frontend/index.html", b"<h1>demo</h1>")
    assert "demo" in make_client(root).get("/").text


# ---------- clips / manifest ----------
def test_synthesized_manifest(client):
    m = client.get("/api/clips/melbourne").json()
    assert m["synthesized"] is True
    assert sorted(r["code"] for r in m["regions"]) == ["JP", "RO", "US"]
    ro = next(r for r in m["regions"] if r["code"] == "RO")
    assert ro["video"] == "output/melbourne_ro.mp4"
    assert ro["video_url"] == "/output/melbourne_ro.mp4"
    assert ro["label"] == "România"
    assert m["ai_view_url"] == "/output/melbourne_ai_view.mp4"


def test_manifest_file_wins(root, client):
    write(root / "output/melbourne.manifest.json", {
        "clip": "melbourne", "ai_view": "output/melbourne_ai_view.mp4",
        "regions": [{"code": "RO", "label": "România", "video": "output/melbourne_ro.mp4",
                     "ad_id": "ro-pizza-bunicii", "reason": "seară ploioasă"}]})
    m = client.get("/api/clips/melbourne").json()
    assert "synthesized" not in m and len(m["regions"]) == 1
    assert m["regions"][0]["reason"] == "seară ploioasă"


def test_bad_manifest_is_422(root, client):
    write(root / "output/melbourne.manifest.json", {"clip": "melbourne", "regions": [{"code": "RO"}]})
    assert client.get("/api/clips/melbourne").status_code == 422


def test_unknown_and_invalid_clip(client):
    assert client.get("/api/clips/nope").status_code == 404
    assert client.get("/api/clips/..%2Fsecret").status_code == 404


def test_list_clips(client):
    assert client.get("/api/clips").json() == [
        {"clip": "melbourne", "regions": ["JP", "RO", "US"], "has_ai_view": True, "synthesized": True}]


def test_video_range_request(client):
    r = client.get("/output/melbourne_ro.mp4", headers={"Range": "bytes=0-9"})
    assert r.status_code == 206 and r.content == b"0123456789"


# ---------- geo / play ----------
def test_play_query_override(client):
    r = client.get("/api/clips/melbourne/play?country=jp").json()
    assert r["current"]["code"] == "JP"
    assert r["viewer"]["source"] == "query"


def test_play_header_and_nearest(client):
    r = client.get("/api/clips/melbourne/play", headers={"X-Demo-Country": "CA"}).json()
    assert r["current"]["code"] == "US"
    assert r["viewer"]["exact_match"] is False


def test_play_default_on_localhost(client):
    r = client.get("/api/clips/melbourne/play").json()
    assert r["viewer"]["source"] == "default" and r["current"]["code"] == "RO"


def test_ip_geolocation(root):
    calls = []
    async def lookup(ip):
        calls.append(ip)
        return "US"
    c = make_client(root, lookup)
    h = {"X-Forwarded-For": "8.8.8.8"}
    assert c.get("/api/geo", headers=h).json() == {"country": "US", "source": "ip", "ip": "8.8.8.8", "region": "US"}
    c.get("/api/geo", headers=h)
    assert calls == ["8.8.8.8"]                                         # cached
    assert c.get("/api/geo", headers={"X-Forwarded-For": "10.0.0.1"}).json()["source"] == "default"


def test_ip_geolocation_failure_falls_back(root):
    async def lookup(ip):
        raise RuntimeError("network down")
    r = make_client(root, lookup).get("/api/geo", headers={"X-Forwarded-For": "8.8.8.8"}).json()
    assert r["source"] == "default" and r["country"] == "RO"


# ---------- scene / surfaces / ads ----------
def test_scene_missing_then_present(root, client):
    assert client.get("/api/clips/melbourne/scene").status_code == 404
    write(root / "output/melbourne.scene.json", {
        "clip": "melbourne", "location": "urban street", "brand_safety": {"safe": True, "reasons": []},
        "choices": {"RO": {"ad_id": "ro-pizza-bunicii", "reason": "stradă aglomerată"}}})
    assert client.get("/api/clips/melbourne/scene").json()["location"] == "urban street"
    # synthesized manifest picks up the choice + play returns the ad
    p = client.get("/api/clips/melbourne/play?country=RO").json()
    assert p["current"]["ad_id"] == "ro-pizza-bunicii"
    assert p["ad"]["brand"] == "Pizza Bunicii"


def test_surfaces_fallback_to_manual_corners(client):
    s = client.get("/api/clips/melbourne/surfaces").json()
    assert s["source"] == "manual" and s["surfaces"][0]["corners"] == CORNERS


def test_surfaces_file_wins(root, client):
    write(root / "output/melbourne.surfaces.json", {"clip": "melbourne", "surfaces": [
        {"id": "s1", "type": "poster", "frame": 0, "corners": CORNERS, "confidence": 0.9}]})
    assert client.get("/api/clips/melbourne/surfaces").json()["surfaces"][0]["type"] == "poster"


def test_ads_sample_and_file(root, client):
    r = client.get("/api/ads?region=us").json()
    assert r["source"] == "sample" and [a["id"] for a in r["ads"]] == ["us-burger-bros"]
    assert client.get("/api/ads/missing").status_code == 404
    write(root / "data/ads.json", [{"id": "x", "region": "RO", "brand": "X"}])
    assert client.get("/api/ads").json()["source"] == "data/ads.json"


# ---------- dashboard ----------
def test_stats(root, client):
    write(root / "output/melbourne.manifest.json", {
        "clip": "melbourne", "regions": [
            {"code": "RO", "video": "output/melbourne_ro.mp4"},
            {"code": "US", "video": "output/melbourne_us.mp4"}],
        "stats": {"frames": 100, "lost_frames": 20, "fps": 25, "width": 1920, "height": 1080}})
    s = client.get("/api/clips/melbourne/stats?views=1000").json()
    assert s["visibility"] == {"ratio": 0.8, "visible_seconds": 3.2, "measured": True}
    assert s["spaces"][0]["frame_share_pct"] > 0
    ro, us = s["regions"]
    assert ro["impressions"] == 800 and ro["revenue_usd"] == 3.2     # 800 * $4 CPM
    assert us["revenue_usd"] == 9.6                                    # 800 * $12 CPM
    assert s["totals"] == {"placements": 2, "revenue_usd": 12.8}
    assert s["cost_vs_value"]["savings_x"] == 3000


def test_unsafe_scene_earns_nothing(root, client):
    write(root / "output/melbourne.scene.json", {"clip": "melbourne",
                                                 "brand_safety": {"safe": False, "reasons": ["accident"]}})
    s = client.get("/api/clips/melbourne/stats").json()
    assert s["totals"]["revenue_usd"] == 0 and s["brand_safety"]["safe"] is False


# ---------- jobs ----------
FAKE_ENGINE = '''
import sys
from pathlib import Path
args = sys.argv[1:]
out = Path(args[args.index("--out") + 1])
regions = [a.split("=")[0] for i, a in enumerate(args) if i and args[i - 1] == "--ad"]
for i in range(30, 91, 30):
    print(f"  {i}/90 frames  (lost so far: 0)", flush=True)
for name in regions + (["ai_view"] if "--debug" in args else []):
    (out.parent / f"{out.name}_{name}.mp4").write_bytes(b"x")
print("frames: 90, billboard lost in 9")
'''


@pytest.fixture
def job_root(root: Path) -> Path:
    write(root / "assets/clips/melbourne.mp4", b"x")
    for code in ("ro", "us", "jp"):
        write(root / f"assets/ads/{code}_portrait.png", b"png")
    write(root / "pipeline/insert_ad.py", FAKE_ENGINE.encode())
    for f in (root / "output").glob("*"):
        f.unlink()
    return root


def test_job_runs_and_writes_manifest(job_root):
    settings = Settings(root=job_root, python=sys.executable)
    runner = JobRunner(settings, Store(settings))
    job = runner.build(JobRequest(clip="melbourne"))
    assert job.regions == ["RO", "US", "JP"]
    runner.run(job)
    assert job.status == "done", (job.error, list(job.log))
    assert job.frames_done == 90
    m = json.loads((job_root / "output/melbourne.manifest.json").read_text(encoding="utf-8"))
    assert [r["code"] for r in m["regions"]] == ["RO", "US", "JP"]
    assert m["regions"][0]["video"] == "output/melbourne_ro.mp4"
    assert m["ai_view"] == "output/melbourne_ai_view.mp4"
    assert m["stats"]["frames"] == 90 and m["stats"]["lost_frames"] == 9


def test_job_prefers_generated_ads(job_root):
    write(job_root / "assets/generated/melbourne/ro.png", b"png")
    settings = Settings(root=job_root)
    job = JobRunner(settings, Store(settings)).build(JobRequest(clip="melbourne"))
    assert any("generated" in a and a.startswith("ro=") for a in job.command)


def test_job_missing_video_is_404(root, client):
    assert client.post("/api/jobs", json={"clip": "melbourne"}).status_code == 404


def test_job_api_end_to_end(job_root):
    c = make_client(job_root)
    r = c.post("/api/jobs", json={"clip": "melbourne", "max_frames": 90})
    assert r.status_code == 202
    job_id = r.json()["id"]
    import time
    for _ in range(100):
        j = c.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("done", "failed"):
            break
        time.sleep(0.1)
    assert j["status"] == "done", j
    assert c.get("/api/clips/melbourne").json()["regions"][0]["video_url"] == "/output/melbourne_ro.mp4"
