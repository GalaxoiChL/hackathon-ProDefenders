"""Generate backend/countries.json: every ISO 3166-1 country with name, flag, currency, language,
continent / subregion (UN M49) and an estimated CPM tier.

The server only reads the JSON; this script (and Babel) is needed only to regenerate it:
    pip install babel
    python backend/tools/build_countries.py
"""
from __future__ import annotations

import json
from pathlib import Path

from babel import Locale
from babel.core import get_global
from babel.numbers import get_territory_currencies

OUT = Path(__file__).resolve().parent.parent / "countries.json"

# UN M49 geoscheme: continent -> subregion -> ISO alpha-2 codes (+ XK Kosovo)
M49: dict[str, dict[str, str]] = {
    "Africa": {
        "Northern Africa": "DZ EG LY MA SD TN EH",
        "Eastern Africa": "IO BI KM DJ ER ET TF KE MG MW MU YT MZ RE RW SC SO SS UG TZ ZM ZW",
        "Middle Africa": "AO CM CF TD CG CD GQ GA ST",
        "Southern Africa": "BW SZ LS NA ZA",
        "Western Africa": "BJ BF CV CI GM GH GN GW LR ML MR NE NG SH SN SL TG",
    },
    "Americas": {
        "Caribbean": "AI AG AW BS BB BQ VG KY CU CW DM DO GD GP HT JM MQ MS PR BL KN LC MF VC SX TT TC VI",
        "Central America": "BZ CR SV GT HN MX NI PA",
        "South America": "AR BO BV BR CL CO EC FK GF GY PY PE GS SR UY VE",
        "Northern America": "BM CA GL PM US",
    },
    "Asia": {
        "Central Asia": "KZ KG TJ TM UZ",
        "Eastern Asia": "CN HK MO KP JP MN KR TW",
        "South-eastern Asia": "BN KH ID LA MY MM PH SG TH TL VN",
        "Southern Asia": "AF BD BT IN IR MV NP PK LK",
        "Western Asia": "AM AZ BH CY GE IQ IL JO KW LB OM QA SA PS SY TR AE YE",
    },
    "Europe": {
        "Eastern Europe": "BY BG CZ HU PL MD RO RU SK UA",
        "Northern Europe": "AX DK EE FO FI GG IS IE IM JE LV LT NO SJ SE GB",
        "Southern Europe": "AL AD BA HR GI GR VA IT MT ME MK PT SM RS SI ES XK",
        "Western Europe": "AT BE FR DE LI LU MC NL CH",
    },
    "Oceania": {
        "Australia and New Zealand": "AU CX CC HM NZ NF",
        "Melanesia": "FJ NC PG SB VU",
        "Micronesia": "GU KI MH FM NR MP PW UM",
        "Polynesia": "AS CK PF NU PN WS TK TO TV WF",
    },
    "Antarctica": {"Antarctica": "AQ"},
}

CONTINENT_RO = {"Africa": "Africa", "Americas": "America", "Asia": "Asia", "Europe": "Europa",
                "Oceania": "Oceania", "Antarctica": "Antarctica"}

# Rough income tiers (World Bank groups) -> assumed CPM of an in-video placement, USD
HIGH = set("AD AE AG AT AU AW BB BE BG BH BM BN BS CA CH CL CW CY CZ DE DK EE ES FI FO FR GB GI GL GR "
           "GU HK HR HU IE IL IM IS IT JP KN KR KW KY LI LT LU LV MC MF MO MP MT NC NL NO NZ OM PA PF "
           "PL PR PT QA RO RU SA SC SE SG SI SK SM SX TC TT TW US UY VG VI".split())
LOW = set("AF BF BI CD CF ER ET GM GN GW KP LR MG ML MW MZ NE RW SD SL SO SS SY TD TG UG YE".split())
CPM_TIER = {"high": 10.0, "middle": 4.0, "low": 1.5}
CPM_OVERRIDE = {"US": 12.0, "JP": 9.0, "GB": 11.0, "DE": 10.5, "RO": 4.0, "CN": 6.0, "IN": 2.0}


def flag(code: str) -> str:
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code)


def primary_language(code: str) -> str | None:
    langs = get_global("territory_languages").get(code, {})
    langs = {k: v for k, v in langs.items() if k != "und"}
    official = {k: v for k, v in langs.items() if v.get("official_status")}
    pool = official or langs
    if not pool:
        return None
    best = max(pool, key=lambda k: pool[k].get("population_percent", 0))
    return best.split("_")[0]


def main() -> None:
    ro, en = Locale("ro").territories, Locale("en").territories
    countries = []
    for continent, subs in M49.items():
        for subregion, codes in subs.items():
            for code in codes.split():
                tier = "high" if code in HIGH else "low" if code in LOW else "middle"
                cur = get_territory_currencies(code)
                countries.append({
                    "code": code,
                    "name": ro.get(code) or en.get(code) or code,
                    "name_en": en.get(code) or code,
                    "flag": flag(code),
                    "currency": cur[0] if cur else None,
                    "language": primary_language(code),
                    "continent": continent,
                    "continent_ro": CONTINENT_RO[continent],
                    "subregion": subregion,
                    "income_tier": tier,
                    "cpm_usd": CPM_OVERRIDE.get(code, CPM_TIER[tier]),
                })
    codes = [c["code"] for c in countries]
    assert len(codes) == len(set(codes)), "duplicate code in M49 table"
    countries.sort(key=lambda c: c["code"])
    OUT.write_text(json.dumps(countries, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT} ({len(countries)} countries)")


if __name__ == "__main__":
    main()
