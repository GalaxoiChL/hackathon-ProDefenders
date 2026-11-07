"""Where regional businesses come from.

- OpenStreetMap (default, free, no key): Nominatim geocodes the city, Overpass lists businesses
  of the requested category that publish a website or email. Data © OpenStreetMap contributors (ODbL).
- Brave Search (optional, BRAVE_API_KEY): web results for "<category> <city>", aggregator sites removed.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from .http import Http

NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = "https://overpass-api.de/api/interpreter"
# public Overpass servers are often "at capacity": try the next one instead of failing the campaign
OVERPASS_MIRRORS = (OVERPASS, "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
                    "https://overpass.kumi.systems/api/interpreter")
CACHE_TTL = 7 * 24 * 3600
# "busy" answers: the server is at capacity or our IP has no free slot right now (overpass-api.de gives
# each IP only a couple of parallel queries). They come back within a second, so waiting and asking
# again usually works, while trying each mirror once made a short spike fail the whole search.
BUSY_STATUS = {429, 502, 503, 504}
RETRY_BUDGET_S = 100      # total time one search may spend on Overpass before giving up
RETRY_PAUSE_S = 6
BRAVE = "https://api.search.brave.com/res/v1/web/search"

# ad category -> OSM tag filters
CATEGORY_TAGS: dict[str, list[str]] = {
    "food": ['["amenity"~"^(restaurant|fast_food|cafe|ice_cream)$"]', '["shop"~"^(bakery|pastry|deli)$"]'],
    "drinks": ['["amenity"~"^(cafe|bar|pub)$"]', '["shop"~"^(coffee|tea|beverages|wine)$"]'],
    "retail": ['["shop"~"^(clothes|shoes|electronics|books|sports|gift|toys|jewelry)$"]'],
    "beauty": ['["shop"~"^(beauty|hairdresser|cosmetics|perfumery)$"]'],
    "fitness": ['["leisure"="fitness_centre"]', '["shop"="sports"]'],
    "hotel": ['["tourism"~"^(hotel|hostel|guest_house)$"]'],
}
CATEGORY_WORDS = {"food": "restaurant", "drinks": "cafe bar", "retail": "shop", "beauty": "beauty salon",
                  "fitness": "gym", "hotel": "hotel"}

# results that are directories / platforms, not the business itself
AGGREGATORS = ("tripadvisor.", "yelp.", "facebook.", "instagram.", "google.", "booking.", "wikipedia.",
               "ubereats.", "deliveroo.", "glovo", "just-eat", "justeat", "foodpanda", "tiktok.", "x.com",
               "twitter.", "linkedin.", "youtube.", "foursquare.", "thefork.", "opentable.", "wolt.",
               "lieferando", "doordash", "grubhub", "tabelog.", "gurunavi", "hotpepper", "maps.", "yellowpages")


@dataclass
class Candidate:
    name: str
    source: str
    source_id: str
    category: str | None = None
    website: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    description: str | None = None
    extra: dict = field(default_factory=dict)


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip().split(";")[0]
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    p = urlparse(url)
    return url if p.netloc and "." in p.netloc else None


def is_aggregator(url: str | None) -> bool:
    host = urlparse(url or "").netloc.lower()
    return any(a in host for a in AGGREGATORS)


class Sources:
    def __init__(self, http: Http, brave_api_key: str = "", cache_dir: Path | None = None,
                 mirrors: tuple[str, ...] = OVERPASS_MIRRORS, retry_budget_s: float = RETRY_BUDGET_S,
                 retry_pause_s: float = RETRY_PAUSE_S, sleep=time.sleep, clock=time.monotonic):
        self.http = http
        self.brave_key = brave_api_key
        self.cache_dir = cache_dir
        self.mirrors = list(mirrors)
        self.retry_budget_s = retry_budget_s
        self.retry_pause_s = retry_pause_s
        self._sleep = sleep
        self._clock = clock
        self._geo_cache: dict[str, tuple[float, float]] = {}
        self._last_nominatim = 0.0

    def geocode(self, city: str, country: str) -> tuple[float, float]:
        key = f"{city}|{country}".lower()
        if key in self._geo_cache:
            return self._geo_cache[key]
        wait = 1.0 - (time.time() - self._last_nominatim)   # Nominatim policy: max 1 request / second
        if wait > 0:
            time.sleep(wait)
        self._last_nominatim = time.time()
        res = self.http.get_json(NOMINATIM, params={"q": city, "countrycodes": country.lower(),
                                                    "format": "json", "limit": 1})
        if not res:
            raise LookupError(f"city not found: {city} ({country})")
        lat, lon = float(res[0]["lat"]), float(res[0]["lon"])
        self._geo_cache[key] = (lat, lon)
        return lat, lon

    def _overpass(self, query: str) -> dict:
        """Ask the mirrors in turn; while some answered "busy", pause and go round again, within a budget."""
        deadline = self._clock() + self.retry_budget_s
        errors: list[str] = []
        while True:
            busy = False
            for url in list(self.mirrors):
                left = deadline - self._clock()
                if left < 5:
                    break
                host = urlparse(url).netloc
                try:
                    # often takes 10-30 s on the public servers
                    data = self.http.post_json(url, {"data": query}, timeout=min(40.0, left))
                    if not isinstance(data, dict) or "elements" not in data:
                        raise ValueError("unexpected answer")
                except Exception as e:
                    status = getattr(getattr(e, "response", None), "status_code", None)
                    busy = busy or status in BUSY_STATUS
                    errors.append(f"{host}: HTTP {status}" if status else f"{host}: {type(e).__name__}")
                    continue
                if url != self.mirrors[0]:           # remember the server that answered
                    self.mirrors.remove(url)
                    self.mirrors.insert(0, url)
                return data
            # only "busy" is worth waiting for; timeouts and bad answers already used their time
            if not busy or deadline - self._clock() < self.retry_pause_s + 10:
                break
            self._sleep(self.retry_pause_s)
        raise RuntimeError("all Overpass servers failed (" + ", ".join(errors[-6:]) + "). "
                           "The public OpenStreetMap servers are overloaded; try again in a minute.")

    def _cached(self, key: str, fn):
        """Same search within a week -> instant answer. If every server is down, an older answer
        for the same search is still better than none (the demo must not depend on Overpass)."""
        if not self.cache_dir:
            return fn()
        path = self.cache_dir / (hashlib.sha1(key.encode()).hexdigest()[:16] + ".json")
        if path.is_file() and time.time() - path.stat().st_mtime < CACHE_TTL:
            return json.loads(path.read_text(encoding="utf-8"))
        try:
            data = fn()
        except RuntimeError:
            if path.is_file():
                return json.loads(path.read_text(encoding="utf-8"))   # stale, but real results
            raise
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return data

    def osm(self, city: str, country: str, category: str, limit: int, radius_m: int = 1500,
            include_chains: bool = False) -> list[Candidate]:
        lat, lon = self.geocode(city, country)
        filters = CATEGORY_TAGS.get(category, sum(CATEGORY_TAGS.values(), []))
        reachable = '[~"^(website|contact:website|email|contact:email)$"~"."]'   # has a website or an email
        parts = "".join(f"nwr{f}{reachable}(around:{radius_m},{lat:.5f},{lon:.5f});" for f in filters)
        query = f"[out:json][timeout:25];({parts});out center tags {max(limit * 4, 20)};"
        data = self._cached(f"osm|{query}", lambda: self._overpass(query))
        out, seen = [], set()
        for el in data.get("elements", []):
            t = el.get("tags", {})
            name = t.get("name")
            if not name or name.lower() in seen:
                continue
            # chains (McDonald's, KFC...) carry a brand:wikidata tag; we want *regional* businesses
            if not include_chains and (t.get("brand:wikidata") or t.get("operator:wikidata")):
                continue
            seen.add(name.lower())
            website = normalize_url(t.get("website") or t.get("contact:website"))
            addr = " ".join(x for x in (t.get("addr:street"), t.get("addr:housenumber"),
                                        t.get("addr:city")) if x) or None
            out.append(Candidate(
                name=name, source="osm", source_id=f"{el.get('type')}/{el.get('id')}",
                category=t.get("amenity") or t.get("shop") or t.get("tourism") or t.get("leisure"),
                website=None if is_aggregator(website) else website,
                email=(t.get("email") or t.get("contact:email") or "").split(";")[0].strip() or None,
                phone=t.get("phone") or t.get("contact:phone"), address=addr,
                description=t.get("description") or t.get("cuisine"),
            ))
        return out

    def brave(self, city: str, category: str, limit: int) -> list[Candidate]:
        if not self.brave_key:
            return []
        q = f"{CATEGORY_WORDS.get(category, category)} {city}"
        data = self.http.get_json(BRAVE, params={"q": q, "count": min(20, limit * 2)},
                                  headers={"X-Subscription-Token": self.brave_key, "Accept": "application/json"})
        out = []
        for r in data.get("web", {}).get("results", []):
            url = normalize_url(r.get("url"))
            if not url or is_aggregator(url):
                continue
            host = urlparse(url).netloc.lower().removeprefix("www.")
            out.append(Candidate(name=(r.get("title") or host).split(" - ")[0].split(" | ")[0][:120],
                                 source="brave", source_id=host, category=category, website=url,
                                 description=r.get("description")))
        return out

    def search(self, city: str, country: str, category: str, limit: int,
               include_chains: bool = False) -> list[Candidate]:
        found, errors = [], []
        for fn in (lambda: self.osm(city, country, category, limit, include_chains=include_chains),
                   lambda: self.brave(city, category, limit)):
            try:
                found += fn()
            except Exception as e:  # one source down must not kill the campaign
                errors.append(str(e))
        if not found and errors:
            raise RuntimeError("; ".join(errors))
        # one candidate per website domain
        uniq, domains = [], set()
        for c in found:
            d = urlparse(c.website or "").netloc.lower().removeprefix("www.")
            if d and d in domains:
                continue
            domains.add(d)
            uniq.append(c)
        return uniq
