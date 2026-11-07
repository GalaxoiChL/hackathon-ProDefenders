"""FastAPI server for the demo.

Run:   python backend/start.py --reload   (or: uvicorn backend.app:app --port 8000 from the repo root)
Docs:  http://localhost:8000/docs
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

# the site's icon: the SwapBoard logo, same as the tab icon in frontend/index.html
FAVICON_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><filter id="p"><feTurbulence type="fractalNoise" baseFrequency=".04" numOctaves="2" seed="7"/><feDisplacementMap in="SourceGraphic" scale="2.4"/></filter><rect width="64" height="64" rx="10" fill="#f7f5f0"/><g filter="url(#p)" fill="none" stroke="#1b1a17" stroke-linecap="round" stroke-linejoin="round"><path d="M5 7.5C20 6 44 6.8 59.5 6L58.8 44.5C42 45.6 22 44.4 5.6 45.2Z" stroke-width="3.2"/><path d="M17 45.5L16.2 59.5M46.5 45L47.8 59.2" stroke-width="3.6"/><circle cx="32" cy="25.5" r="14.5" stroke-width="2.6"/></g><g filter="url(#p)" fill="none" stroke="#8a1c1c" stroke-width="3" stroke-linecap="round"><path d="M13 34C17 18 27 10 37 15.5C44 19 48 16 52.5 11.5"/></g><g fill="#8a1c1c"><circle cx="13" cy="34" r="3.2"/><circle cx="37" cy="15.5" r="3.2"/><circle cx="52.5" cy="11.5" r="3.2"/></g></svg>'

from . import regions
from .config import Settings
from .geo import GeoResolver
from .jobs import JobRunner
from .models import JobRequest, Manifest
from .stats import clip_stats
from .store import BadData, BadRequest, NotFound, Store, url_for


def manifest_out(m: Manifest) -> dict:
    """Manifest as in the contract, plus ready-to-use URLs for the frontend."""
    data = m.model_dump(exclude_none=True)
    data["ai_view_url"] = url_for(m.ai_view)
    for r in data["regions"]:
        r["video_url"] = url_for(r["video"])
        r.setdefault("label", regions.label(r["code"]))
        r["flag"] = regions.flag(r["code"])
    return data


def create_app(settings: Settings | None = None, geo: GeoResolver | None = None,
               outreach_settings=None, outreach_http=None, outreach_llm=None) -> FastAPI:
    settings = settings or Settings.from_env()
    store = Store(settings)
    geo = geo or GeoResolver(settings)
    jobs = JobRunner(settings, store)

    app = FastAPI(title="ProDefenders API",
                  description="Reclame în video adaptate țării privitorului. API între pipeline și demo.",
                  version="1.0.0")
    app.state.settings, app.state.store, app.state.jobs = settings, store, jobs
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                       allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(NotFound)
    async def _not_found(_: Request, exc: NotFound):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(BadRequest)
    async def _bad_request(_: Request, exc: BadRequest):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    def country_or_400(code: str) -> dict:
        c = regions.get(code)
        if not c:
            raise BadRequest(f"unknown country code: {code!r} (use ISO 3166-1 alpha-2, e.g. FR)")
        return c

    @app.exception_handler(BadData)
    async def _bad_data(_: Request, exc: BadData):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    # ---------------- meta ----------------
    @app.get("/api/health", tags=["meta"])
    def health():
        ads, ads_source = store.ads()
        return {"status": "ok", "clips": store.list_clips(), "ads": len(ads), "ads_source": ads_source,
                "countries": len(regions.countries()), "markets": list(settings.markets),
                "output_dir": settings.output_dir.is_dir(), "default_region": settings.default_region,
                "geo_enabled": settings.geo_enabled,
                "jobs_running": sum(j.status == "running" for j in jobs.jobs.values())}

    # ---------------- countries ----------------
    @app.get("/api/countries", tags=["countries"],
             summary="Toate țările lumii (ISO 3166-1), pentru selectorul de țară")
    def list_countries(q: str | None = Query(None, description="caută după cod sau nume (RO/EN)"),
                       continent: str | None = Query(None, description="ex: Europe / Europa")):
        return regions.search(q, continent)

    @app.get("/api/markets", tags=["countries"],
             summary="Piețele demo (US, RO, JP + 12 din Europa): opțiunile din selectorul de țară")
    def list_markets():
        ads = store.ads()[0]
        out = []
        for code in settings.markets:
            c = regions.get(code)
            own = [a for a in ads if a.region.upper() == code]
            out.append({**c, "default": code == settings.default_region,
                        "ads": len(own), "brand": own[0].brand if own else None})
        return out

    @app.get("/api/countries/{code}", tags=["countries"])
    def get_country(code: str):
        return country_or_400(code)

    @app.get("/api/geo", tags=["countries"],
             summary="Țara privitorului (query > header > Cloudflare > IP > default)")
    async def viewer_geo(request: Request, country: str | None = Query(None, min_length=2, max_length=2)):
        if country:
            country_or_400(country)
        g = await geo.resolve(request, country)
        market, match = regions.resolve(g["country"], list(settings.markets), settings.default_region)
        return {**g, "details": regions.get(g["country"]), "market": market, "market_match": match,
                "market_details": regions.get(market)}

    # ---------------- clips ----------------
    @app.get("/api/clips", tags=["clips"])
    def list_clips():
        out = []
        for name in store.list_clips():
            try:
                m = store.manifest(name)
            except (NotFound, BadData):
                continue
            out.append({"clip": name, "regions": [r.code for r in m.regions],
                        "has_ai_view": bool(m.ai_view), "synthesized": bool(getattr(m, "synthesized", False))})
        return out

    @app.get("/api/clips/{clip}", tags=["clips"], summary="Manifestul clipului + URL-uri video")
    def get_manifest(clip: str):
        return manifest_out(store.manifest(clip))

    @app.get("/api/clips/{clip}/play", tags=["clips"],
             summary="Ce versiune vede privitorul acesta (după geolocație sau ?country=)")
    async def play(clip: str, request: Request,
                   country: str | None = Query(None, min_length=2, max_length=2)):
        if country:
            country_or_400(country)
        m = manifest_out(store.manifest(clip))
        g = await geo.resolve(request, country)
        codes = [r["code"] for r in m["regions"]]
        chosen, match = regions.resolve(g["country"], codes, settings.default_region)
        current = next(r for r in m["regions"] if r["code"].upper() == chosen)
        ad = None
        if current.get("ad_id"):
            try:
                ad = store.ad(current["ad_id"]).model_dump()
            except NotFound:
                pass
        viewer = regions.get(g["country"]) or {}
        return {"clip": clip,
                "viewer": {**g, "name": viewer.get("name"), "flag": viewer.get("flag"),
                           "market": regions.resolve(g["country"], list(settings.markets),
                                                     settings.default_region)[0],
                           "region": chosen, "match": match, "match_label": regions.MATCH_LABELS[match],
                           "exact_match": match == "exact"},
                "current": current, "ad": ad, "ai_view_url": m["ai_view_url"], "regions": m["regions"]}

    @app.get("/api/clips/{clip}/scene", tags=["clips"], summary="Analiza scenei + brand safety (task 2)")
    def get_scene(clip: str):
        return store.scene(clip).model_dump()

    @app.get("/api/clips/{clip}/surfaces", tags=["clips"], summary="Spațiile publicitare detectate")
    def get_surfaces(clip: str):
        return store.surfaces(clip).model_dump()

    @app.get("/api/clips/{clip}/stats", tags=["dashboard"],
             summary="Dashboard advertiser: spații, vizibilitate, venit estimat, cost vs. valoare")
    def get_stats(clip: str, views: int = Query(None, ge=0, le=1_000_000_000)):
        m = store.manifest(clip)
        return clip_stats(settings, m, store.surfaces_or_none(clip), store.scene_or_none(clip),
                          store.ads()[0], views if views is not None else settings.default_views)

    # ---------------- ads ----------------
    @app.get("/api/ads", tags=["ads"])
    def list_ads(region: str | None = None):
        ads, source = store.ads()
        if region:
            ads = [a for a in ads if a.region.upper() == region.upper()]
        return {"source": source, "ads": [a.model_dump() for a in ads]}

    @app.get("/api/ads/{ad_id}", tags=["ads"])
    def get_ad(ad_id: str):
        return store.ad(ad_id).model_dump()

    # ---------------- jobs ----------------
    @app.post("/api/jobs", tags=["jobs"], status_code=202,
              summary="Pornește pipeline-ul pentru un clip (în fundal); scrie manifest.json la final")
    def create_job(req: JobRequest):
        return jobs.submit(req).public()

    @app.get("/api/jobs", tags=["jobs"])
    def list_jobs():
        return [j.public(log_lines=3) for j in sorted(jobs.jobs.values(), key=lambda j: -j.created)]

    @app.get("/api/jobs/{job_id}", tags=["jobs"])
    def get_job(job_id: str, log_lines: int = Query(20, ge=0, le=200)):
        job = jobs.jobs.get(job_id)
        if not job:
            raise HTTPException(404, f"no job {job_id!r}")
        return job.public(log_lines)

    # ---------------- outreach: lead search, emails, bidding ----------------
    from .outreach.routes import build as build_outreach  # noqa: PLC0415
    router, app.state.outreach = build_outreach(settings, store, outreach_settings, outreach_http, outreach_llm)
    app.include_router(router)

    # ---------------- files ----------------
    # Some browsers ask for /favicon.ico whatever the page declares: same icon as frontend/index.html.
    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return Response(FAVICON_SVG, media_type="image/svg+xml",
                        headers={"Cache-Control": "public, max-age=86400"})

    # The site asks for output/index.json to list rendered clips; answer from the store (JSON, not 404).
    @app.get("/output/index.json", include_in_schema=False)
    def output_index():
        return {"clips": store.list_clips()}

    # Starlette's FileResponse answers Range requests, so <video> seeking works.
    app.mount("/output", StaticFiles(directory=settings.output_dir, check_dir=False), name="output")
    # /assets is shared by backend/assets (clips, ads) and the built site's JS/CSS (frontend/dist/assets,
    # Vite's default folder). Without the build folder the page loads blank: look there first.
    assets = StaticFiles(directory=settings.assets_dir, check_dir=False)
    built_assets = settings.frontend_dir / "assets"
    if (settings.frontend_dir / "index.html").is_file() and built_assets.is_dir():
        assets.all_directories.insert(0, built_assets)
    app.mount("/assets", assets, name="assets")
    app.mount("/data", StaticFiles(directory=settings.data_dir, check_dir=False), name="data")
    # team clips (catalog.js, index.json, videos): the site loads them at /media, as with the Vite server
    app.mount("/media", StaticFiles(directory=settings.media_dir, check_dir=False), name="media")

    index = settings.frontend_dir / "index.html"
    if index.is_file() and "/src/main" not in index.read_text(encoding="utf-8", errors="ignore"):
        # task 3's build/static files, served from the same origin (no CORS issues on demo day)
        app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
    else:
        @app.get("/", include_in_schema=False)
        def root():
            return {"name": "ProDefenders API", "docs": "/docs", "health": "/api/health"}

    return app


app = create_app()
