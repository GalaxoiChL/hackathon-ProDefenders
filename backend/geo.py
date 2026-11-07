"""Viewer country detection.

Order of precedence (first one that answers wins):
  1. `?country=XX` query parameter        (demo: switch country by hand)
  2. `X-Demo-Country` header              (demo: frontend selector)
  3. `CF-IPCountry` header                (if deployed behind Cloudflare)
  4. IP geolocation (ip-api.com, cached)  (the real thing)
  5. DEFAULT_REGION                       (offline / localhost / lookup failed)
"""
from __future__ import annotations

import ipaddress
import re
from typing import Awaitable, Callable

import httpx
from fastapi import Request

from .config import Settings

COUNTRY_RE = re.compile(r"^[A-Za-z]{2}$")
Lookup = Callable[[str], Awaitable[str | None]]


def client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else None


def is_public(ip: str | None) -> bool:
    try:
        addr = ipaddress.ip_address(ip or "")
    except ValueError:
        return False
    return addr.is_global


def _country(value: str | None) -> str | None:
    if value and COUNTRY_RE.match(value.strip()) and value.strip().upper() != "XX":
        return value.strip().upper()
    return None


class GeoResolver:
    def __init__(self, settings: Settings, lookup: Lookup | None = None):
        self.settings = settings
        self._lookup = lookup or self._http_lookup
        self._cache: dict[str, str | None] = {}

    async def _http_lookup(self, ip: str) -> str | None:
        url = self.settings.geo_url.format(ip=ip)
        async with httpx.AsyncClient(timeout=self.settings.geo_timeout) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
        if data.get("status", "success") != "success":
            return None
        return _country(data.get("countryCode") or data.get("country_code"))

    async def lookup_ip(self, ip: str) -> str | None:
        if ip in self._cache:
            return self._cache[ip]
        try:
            country = await self._lookup(ip)
        except Exception:  # network down, rate limit, bad JSON: never break the demo
            return None    # not cached, so a later request can retry
        if len(self._cache) > 10_000:
            self._cache.clear()
        self._cache[ip] = country
        return country

    async def resolve(self, request: Request, override: str | None = None) -> dict:
        ip = client_ip(request)
        for source, value in (
            ("query", override),
            ("header", request.headers.get("x-demo-country")),
            ("cloudflare", request.headers.get("cf-ipcountry")),
        ):
            c = _country(value)
            if c:
                return {"country": c, "source": source, "ip": ip}
        if self.settings.geo_enabled and is_public(ip):
            c = await self.lookup_ip(ip)
            if c:
                return {"country": c, "source": "ip", "ip": ip}
        return {"country": self.settings.default_region, "source": "default", "ip": ip}
