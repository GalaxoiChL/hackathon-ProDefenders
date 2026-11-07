"""Every country in the world, and which rendered version a viewer from any of them sees.

A "region" is simply the country code a clip was rendered for (output/<clip>_<cc>.mp4).
Any ISO 3166-1 country can have its own version; viewers from countries without one get
the closest rendered version, scored in this order:

    exact country > same language > same subregion (UN M49) > same continent > default region

Country data lives in countries.json (regenerate with backend/tools/build_countries.py).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

COUNTRIES_FILE = Path(__file__).resolve().parent / "countries.json"
FALLBACK_CPM_USD = 4.0

MATCH_LABELS = {
    "exact": "versiunea țării tale",
    "language": "aceeași limbă",
    "subregion": "aceeași zonă geografică",
    "continent": "același continent",
    "default": "versiunea implicită",
}


@lru_cache(maxsize=1)
def countries() -> dict[str, dict]:
    data = json.loads(COUNTRIES_FILE.read_text(encoding="utf-8"))
    return {c["code"]: c for c in data}


def is_country(code: str | None) -> bool:
    return bool(code) and code.upper() in countries()


def get(code: str) -> dict | None:
    return countries().get(code.upper())


def label(code: str) -> str:
    c = get(code)
    return c["name"] if c else code.upper()


def flag(code: str) -> str | None:
    c = get(code)
    return c["flag"] if c else None


def cpm_usd(code: str) -> float:
    c = get(code)
    return c["cpm_usd"] if c else FALLBACK_CPM_USD


def search(q: str | None = None, continent: str | None = None) -> list[dict]:
    """Countries sorted by Romanian name; `q` matches code, Romanian or English name."""
    items = list(countries().values())
    if continent:
        cont = continent.lower()
        items = [c for c in items if cont in (c["continent"].lower(), c["continent_ro"].lower())]
    if q:
        ql = q.strip().lower()
        items = [c for c in items
                 if ql == c["code"].lower() or ql in c["name"].lower() or ql in c["name_en"].lower()]
    return sorted(items, key=lambda c: c["name"])


def resolve(country: str | None, available: list[str], default: str) -> tuple[str | None, str | None]:
    """(rendered region code, match kind) for a viewer from `country`."""
    avail = [a.upper() for a in available]
    if not avail:
        return None, None
    viewer = get(country) if country else None
    if viewer and viewer["code"] in avail:
        return viewer["code"], "exact"

    default = default.upper()
    kinds = ("language", "subregion", "continent")

    def score(code: str) -> tuple:
        cand = get(code) or {}
        same = [bool(viewer) and cand.get(k) is not None and cand.get(k) == viewer.get(k)
                for k in kinds]
        return (*same, code == default)

    best = max(avail, key=score)  # max keeps the first on ties, i.e. the manifest order
    s = score(best)
    for kind, hit in zip(kinds, s):
        if hit:
            return best, kind
    return best, "default"


def region_for_country(country: str | None, available: list[str], default: str) -> str | None:
    return resolve(country, available, default)[0]
