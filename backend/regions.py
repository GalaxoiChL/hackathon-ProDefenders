"""Demo regions and how a viewer's country maps onto them."""
from __future__ import annotations

# cpm_usd: assumed price per 1000 impressions of an in-video placement, used by the dashboard
REGIONS: dict[str, dict] = {
    "RO": {"label": "România", "flag": "🇷🇴", "currency": "RON", "cpm_usd": 4.0},
    "US": {"label": "SUA", "flag": "🇺🇸", "currency": "USD", "cpm_usd": 12.0},
    "JP": {"label": "Japonia", "flag": "🇯🇵", "currency": "JPY", "cpm_usd": 9.0},
}

# countries without their own version fall back to the closest demo market
NEAREST: dict[str, str] = {
    "MD": "RO", "BG": "RO", "HU": "RO", "RS": "RO", "UA": "RO",
    "CA": "US", "MX": "US", "GB": "US", "IE": "US", "AU": "US", "NZ": "US",
    "KR": "JP", "TW": "JP", "CN": "JP", "HK": "JP",
}


def label(code: str) -> str:
    return REGIONS.get(code.upper(), {}).get("label", code.upper())


def region_for_country(country: str | None, available: list[str], default: str) -> str | None:
    """Pick which rendered version a viewer from `country` should see.

    `available` is the list of region codes the clip was rendered for.
    """
    if not available:
        return None
    avail = [a.upper() for a in available]
    if country:
        c = country.upper()
        if c in avail:
            return c
        near = NEAREST.get(c)
        if near in avail:
            return near
    if default.upper() in avail:
        return default.upper()
    return avail[0]
