"""P2B.S3a — enumerate & curate the full World Bank WDI catalogue.

Session-A of the two-part "World Bank full mirror" step. This script does NOT
touch the warehouse. It answers one question for every indicator World Bank
publishes in source 2 (World Development Indicators):

    "Does Nepal actually have recent data for this, and can we place it in our
     model (a unit + one of our 8 sectors) WITHOUT guessing?"

and writes the answer to two reviewable files:

  * ``db/seeds/indicators_wb_full.csv``  — the KEEP list (has Nepal data, unit
    and sector both resolved by the fixed rules below). This is the seed the
    Session-B loader (P2B.S3b) will ingest.
  * ``reference/worldbank/unmapped_report.csv`` — every indicator that HAS Nepal
    data but whose unit or sector could not be resolved by the rules. These are
    reported, never force-loaded (non-negotiable rule #1: never guess).

Fixed rules (from docs/steps/phase-2b-expansion-steps.md P2B.S3):

  KEEP if: at least one non-null Nepal value dated >= 2000 AND the indicator is
  a live source-2 (WDI) indicator (archived indicators are excluded by only
  enumerating source 2).

  UNIT INFERENCE (first match wins, most-specific first; see resolve_unit for
  the exact order — PPP before US$, rates before areas, density before a bare
  population headcount). Resolves to PCT, USD, USD_PPP, LCU, MT_CO2E, YEARS,
  DAYS, the PER_* rate family, SQ_KM/HECTARES/METRIC_TONS/KWH, SCORE, INDEX,
  COUNT (explicit '(number)'/'number of' or a known count-noun), and PERSONS
  (a population figure with no other unit). Anything unresolved -> unmapped.

  SECTOR MAPPING, in this order (unresolved -> unmapped):

  1. Demography override. WB publishes no "Population" topic — it files age
     structure under Health, the urban split under Climate Change and the rural
     split under Agriculture. The SP.POP./SP.RUR./SP.URB./SM.POP. families plus
     a short named list (birth/death/fertility rates, population density) are
     therefore re-shelved to `population`, minus two explicit exceptions
     (R&D researchers/technicians). See DEMOGRAPHY_* below.
  2. The WB topic on the indicator:
    Economy & Growth / Financial Sector / Trade / External Debt /
      Public Sector / Poverty / Science & Technology / Infrastructure -> economy
    Health / Nutrition / Health & Population dynamics                 -> health
    Education                                                         -> education
    Labor & Social Protection                                        -> labor
    Agriculture & Rural Development                                   -> agriculture
    Environment / Energy & Mining / Climate Change / Urban Development-> environment
    Gender / Social Development                                       -> population
  3. Code-family fallback, used ONLY when WB supplies no topic at all. The
     first segment of a WDI code is WB's own topic family, so this reads their
     classification off the code instead of guessing from the name. This is what
     places the Worldwide Governance Indicators (GOV_WGI_*) in `governance`.

Everything is cached under ``.cache/wb_catalog/`` (git-ignored) so the run is
resumable and never hammers the WB API: re-running only fetches codes not yet
cached. Idempotent — the output CSVs are rewritten deterministically each run.

Run with ``make wb-catalog`` (or ``python -m scripts.wb_catalog``). Add
``--limit N`` for a quick smoke test over the first N indicators.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from ingestion.common.io_utf8 import configure_stdout_utf8

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / ".cache" / "wb_catalog"
KEEP_CSV = REPO_ROOT / "db" / "seeds" / "indicators_wb_full.csv"
UNMAPPED_CSV = REPO_ROOT / "reference" / "worldbank" / "unmapped_report.csv"

SOURCE = "2"  # World Development Indicators (the live WDI database)
COUNTRY = "NPL"
LIST_URL = f"https://api.worldbank.org/v2/source/{SOURCE}/indicator"
PRESENCE_URL = "https://api.worldbank.org/v2/country/{country}/indicator/{code}"
MIN_YEAR = 2000
REQUEST_PAUSE_S = 0.05  # politeness between live fetches; cached codes skip it
FETCH_WORKERS = 8  # gentle concurrency to warm the cache (WB tolerates this)

# WB topic value (normalised: lower-cased, '&'->'and', collapsed spaces) -> sector.
TOPIC_TO_SECTOR: dict[str, str] = {
    "economy and growth": "economy",
    "financial sector": "economy",
    "trade": "economy",
    "external debt": "economy",
    "public sector": "economy",
    "poverty": "economy",
    "science and technology": "economy",
    "infrastructure": "economy",
    "private sector": "economy",
    "health": "health",
    "nutrition": "health",
    "education": "education",
    "labor and social protection": "labor",
    "social protection and labor": "labor",  # WB's current name for the same topic
    "aid effectiveness": "economy",  # ODA / external finance flows
    "agriculture and rural development": "agriculture",
    "environment": "environment",
    "energy and mining": "environment",
    "climate change": "environment",
    "urban development": "environment",
    "gender": "population",
    "social development": "population",
}

# --- Demography re-shelving -------------------------------------------------
# WB has no "Population" topic. It files age structure and the urban/rural split
# under Health, Climate Change and Agriculture, which would leave our People
# sector (decision 0003) nearly empty while Health absorbed ~70 age-band rows.
# These families ARE demography wherever WB shelves them. Keyed on the WDI code
# family — WB's own documented convention — not on a reading of the name.
DEMOGRAPHY_PREFIXES: tuple[str, ...] = (
    "SP.POP.",  # population totals, age bands, dependency ratios, sex ratio
    "SP.RUR.",  # rural population
    "SP.URB.",  # urban population
    "SM.POP.",  # migration, refugees, displacement
)
# Individually named because their family (SP.DYN / EN.POP) is mostly health or
# environment: these specific series are pure demography.
DEMOGRAPHY_CODES: frozenset[str] = frozenset(
    {
        "SP.DYN.CBRT.IN",  # crude birth rate
        "SP.DYN.CDRT.IN",  # crude death rate
        "SP.DYN.TFRT.IN",  # total fertility rate
        "SP.DYN.WFRT",  # wanted fertility rate
        "EN.POP.DNST",  # population density
    }
)
# ...and these carry a demographic code but are not demography.
DEMOGRAPHY_EXCEPTIONS: frozenset[str] = frozenset(
    {
        "SP.POP.SCIE.RD.P6",  # researchers in R&D -> Science & Technology
        "SP.POP.TECH.RD.P6",  # technicians in R&D -> Science & Technology
    }
)

# --- Code-family fallback ---------------------------------------------------
# Used ONLY when WB publishes an indicator with no topic at all (121 of them,
# including the whole Worldwide Governance Indicators family). The first segment
# of a WDI code is WB's own topic family, so this reads their classification off
# the code rather than guessing from the name. An unknown family still falls
# through to the unmapped report.
CODE_FAMILY_TO_SECTOR: dict[str, str] = {
    "SH": "health",
    "SE": "education",
    "SL": "labor",
    "SP": "population",
    "SM": "population",
    "AG": "agriculture",
    "EN": "environment",
    "EG": "environment",
    "ER": "environment",
    "GOV": "governance",  # Worldwide Governance Indicators (GOV_WGI_*)
    "GD": "governance",  # Women, Business and the Law legal-framework indices
    "VC": "governance",  # conflict, violence, rule of law
    "IC": "economy",  # business environment / B-READY
    "SI": "economy",  # poverty & income distribution
    "DT": "economy",  # external debt
    "DC": "economy",  # development co-operation / aid flows
    "NE": "economy",
    "NY": "economy",
    "NV": "economy",
    "PA": "economy",  # PPP conversion factors, price levels
    "BX": "economy",
    "BN": "economy",
    "BM": "economy",
    "FI": "economy",
    "FM": "economy",
    "FP": "economy",
    "FR": "economy",
    "FS": "economy",
    "FB": "economy",
    "GC": "economy",  # government finance
    "IE": "economy",
    "IS": "economy",  # infrastructure
    "IT": "economy",  # ICT
    "MS": "economy",  # military
    "TX": "economy",
    "TM": "economy",
    "TG": "economy",
    "CM": "economy",
}
# The Human Capital Index ships pillar scores with no topic; the pillar is named
# in the code, so each pillar goes to its own sector. The composite HCI rows
# span both pillars and are left unmapped rather than forced into one.
HCI_PILLAR_TO_SECTOR: dict[str, str] = {
    "HD_HCIP_EDUC": "education",
    "HD_HCIP_HLTH": "health",
    "HD_HCIP_OTJL": "labor",  # on-the-job learning
}

# The 20 WDI codes already curated by hand in db/seeds/indicators.csv. Excluded
# from the full catalogue so the two seed files stay disjoint and those codes'
# identities stay stable (P2B.S3b keeps them as-is).
ALREADY_SEEDED: frozenset[str] = frozenset(
    {
        "NY.GDP.MKTP.CD", "NY.GDP.MKTP.KD.ZG", "NY.GDP.PCAP.CD", "FP.CPI.TOTL.ZG",
        "SP.POP.TOTL", "SP.POP.GROW", "SP.DYN.LE00.IN", "SP.DYN.IMRT.IN",
        "SE.ADT.LITR.ZS", "SE.PRM.ENRR", "SL.UEM.TOTL.ZS", "BX.TRF.PWKR.CD.DT",
        "BX.TRF.PWKR.DT.GD.ZS", "NE.EXP.GNFS.ZS", "NE.IMP.GNFS.ZS",
        "FI.RES.TOTL.CD", "SP.URB.TOTL.IN.ZS", "EG.ELC.ACCS.ZS",
        "IT.NET.USER.ZS", "BX.KLT.DINV.CD.WD",
    }
)


@dataclass(frozen=True)
class Indicator:
    """One WDI indicator's metadata as WB publishes it."""

    code: str
    name: str
    unit: str
    topics: tuple[str, ...]


@dataclass(frozen=True)
class Presence:
    """Nepal's most-recent non-empty value for an indicator (from mrnev=1)."""

    latest_year: int | None
    latest_value: float | None


def normalise_topic(value: str) -> str:
    return " ".join(value.replace("&", "and").lower().split())


# Nouns that mark a plain headcount when no explicit unit string is present.
COUNT_NOUNS: tuple[str, ...] = (
    "subscriptions", "applications", "journal articles", "personnel",
    "pupils", "teachers", "secure internet servers", "departures",
    "passengers carried", "labor force", "labour force", "out of school",
    "species", "migrant stock", "net migration", "armed forces",
    "deaths", "cases", "new hiv infections",
    "living with hiv", "newly infected", "asylum-seekers",
    "displaced people", "refugee population", "refugees",
)


def resolve_unit(name: str, unit: str) -> str | None:
    """Map a WDI name/unit string to one of our unit codes, or None if the fixed
    rules cannot resolve it (caller then reports it, never guesses).

    Order matters: more specific patterns (PPP before US$, rates before areas,
    per-sq-km density before a bare population headcount) are tested first.
    """
    lname = name.lower()
    # --- shares / rates expressed as percentages ---
    if "%" in name or "%" in unit:
        return "PCT"
    # --- money ---
    if "ppp" in lname and ("$" in name or "international" in lname):
        return "USD_PPP"
    if "US$" in name or "current usd" in lname:
        return "USD"
    if "lcu" in lname:
        return "LCU"
    # --- explicit rate/scale families ---
    if "per 1,000 live births" in lname:
        return "PER_1000_LIVE_BIRTHS"
    if "co2e" in lname:
        return "MT_CO2E"
    if "(years)" in lname:
        return "YEARS"
    if "(days)" in lname:
        return "DAYS"
    if "per 100,000" in lname:
        return "PER_100K"
    if "per 1,000" in lname or "per 1000" in lname:
        return "PER_1000"
    if "per 100 people" in lname:
        return "PER_100"
    if "per million" in lname or "per 1 million" in lname:
        return "PER_MILLION"
    if "births per woman" in lname:
        return "BIRTHS_PER_WOMAN"
    if "hours per week" in lname:
        return "HOURS_PER_WEEK"
    if "months of imports" in lname:
        return "MONTHS_OF_IMPORTS"
    # --- physical quantities (density before area/headcount) ---
    if "per sq. km" in lname or "per square kilom" in lname:
        return "PER_KM2"  # e.g. population density (people per sq. km)
    # compound "X per Y" units before the bare quantity they contain
    if "kilograms per hectare" in lname or "kg per hectare" in lname:
        return "KG_PER_HECTARE"
    if "hectares per person" in lname:
        return "HECTARES_PER_PERSON"
    if "mm per year" in lname:
        return "MM_PER_YEAR"
    if "kwh per capita" in lname:
        return "KWH_PER_CAPITA"
    if "kg of oil equivalent per capita" in lname:
        return "KG_OE_PER_CAPITA"
    if "micrograms per cubic meter" in lname:
        return "UG_PER_M3"
    if "billion cubic meters" in lname:
        return "BILLION_M3"
    if "cubic meters" in lname and "per capita" in lname:
        return "M3_PER_CAPITA"
    if "liters of pure alcohol" in lname:
        return "LITRES_PER_CAPITA"
    if "ton-km" in lname:
        return "MILLION_TON_KM"
    if "(sq. km" in lname:
        return "SQ_KM"
    if "(hectares)" in lname:
        return "HECTARES"
    if "(metric tons)" in lname:
        return "METRIC_TONS"
    if "(kwh)" in lname:
        return "KWH"
    # --- indices and ordinal scores ---
    if "cpia" in lname or "1=low" in lname or "1-5 scale" in lname or "(spi)" in lname:
        return "SCORE"
    if "index" in lname or "(gpi)" in lname or "gini" in lname or "deflator" in lname:
        return "INDEX"
    # ordinal/bounded scales that name no unit of their own (WGI, HCI, B-READY)
    if "score" in lname or "(scale" in lname or "governance estimate" in lname:
        return "SCORE"
    # NB: whole word only — a substring test also matches "migration",
    # "agglomerations" and "operational", which are not ratios.
    if re.search(r"\bratio\b", lname):
        return "RATIO"  # pupil-teacher, sex ratio at birth, broad money/reserves
    # --- plain counts ---
    if "(number)" in lname or "number of" in lname:
        return "COUNT"
    if any(noun in lname for noun in COUNT_NOUNS):
        return "COUNT"
    if "population" in lname:
        return "PERSONS"  # a population figure not otherwise unitised is a headcount
    return None


def code_family(wdi_code: str) -> str:
    """WB's own topic family: the first segment of the code. Most WDI codes are
    dotted (``SH.STA.ODFC.ZS``); the newer collections are underscored
    (``GOV_WGI_CC_EST``)."""
    head = wdi_code.split(".", 1)[0]
    return head.split("_", 1)[0] if "_" in head else head


def resolve_sector(wdi_code: str, topics: tuple[str, ...]) -> str | None:
    """Map an indicator to one of our 8 sectors, or None (reported, never
    guessed).

    Order: demography override first (WB has no Population topic), then WB's own
    topic, then — only when WB supplies no topic at all — the code family.
    """
    if wdi_code not in DEMOGRAPHY_EXCEPTIONS and (
        wdi_code.startswith(DEMOGRAPHY_PREFIXES) or wdi_code in DEMOGRAPHY_CODES
    ):
        return "population"
    for topic in topics:
        sector = TOPIC_TO_SECTOR.get(normalise_topic(topic))
        if sector is not None:
            return sector
    if topics:
        return None  # WB classified it; we simply do not recognise the topic
    for prefix, sector in HCI_PILLAR_TO_SECTOR.items():
        if wdi_code.startswith(prefix):
            return sector
    return CODE_FAMILY_TO_SECTOR.get(code_family(wdi_code))


def our_code(wdi_code: str) -> str:
    """Deterministic, stable internal code derived from the WDI code."""
    return wdi_code.replace(".", "_")


def fetch_indicator_list() -> list[Indicator]:
    """All indicators in WB source 2, one paged request. Cached."""
    cache = CACHE_DIR / "_indicator_list.json"
    if cache.exists():
        payload = json.loads(cache.read_text(encoding="utf-8"))
    else:
        resp = requests.get(
            LIST_URL, params={"format": "json", "per_page": "20000"}, timeout=120
        )
        resp.raise_for_status()
        payload = resp.json()
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(payload), encoding="utf-8")
    if not isinstance(payload, list) or len(payload) < 2:
        raise RuntimeError(f"unexpected WB indicator list: {payload!r:.200}")
    indicators: list[Indicator] = []
    for row in payload[1] or []:
        topics = tuple(
            t.get("value", "").strip()
            for t in (row.get("topics") or [])
            if isinstance(t, dict) and t.get("value", "").strip()
        )
        indicators.append(
            Indicator(
                code=row["id"],
                name=(row.get("name") or "").strip(),
                unit=(row.get("unit") or "").strip(),
                topics=topics,
            )
        )
    return indicators


def _get_with_retries(url: str, params: dict[str, str], attempts: int = 4) -> Any:
    """GET returning parsed JSON, retrying transient network errors with a short
    exponential backoff. Never hammers: backs off before each retry."""
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:  # timeout, 5xx, connection reset
            last = exc
            time.sleep(1.0 * (attempt + 1))
    raise last if last is not None else RuntimeError("unreachable")


def _warm_one(code: str) -> str | None:
    """Fetch+cache one code's presence. Returns the code on persistent failure
    (so the caller can report it), or None on success. Non-fatal by design."""
    try:
        fetch_presence(code)
        return None
    except requests.RequestException:
        return code


def fetch_presence(code: str) -> Presence:
    """Nepal's most-recent non-empty value for one code (mrnev=1). Cached."""
    cache = CACHE_DIR / f"{code}.json"
    if cache.exists():
        payload = json.loads(cache.read_text(encoding="utf-8"))
    else:
        payload = _get_with_retries(
            PRESENCE_URL.format(country=COUNTRY, code=code),
            {"format": "json", "per_page": "1", "mrnev": "1"},
        )
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(payload), encoding="utf-8")
        time.sleep(REQUEST_PAUSE_S)
    if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
        return Presence(latest_year=None, latest_value=None)
    row = payload[1][0]
    value = row.get("value")
    date = row.get("date")
    try:
        year = int(date) if date is not None else None
    except (ValueError, TypeError):
        year = None
    return Presence(
        latest_year=year,
        latest_value=float(value) if value is not None else None,
    )


def build_catalogue(limit: int | None) -> dict[str, int]:
    """Enumerate, presence-check, curate, and write both output CSVs. Returns
    the summary counts."""
    indicators = fetch_indicator_list()
    print(f"WB source {SOURCE} publishes {len(indicators)} indicators.")
    if limit is not None:
        indicators = indicators[:limit]
        print(f"  (--limit {limit}: only checking the first {len(indicators)})")

    kept: list[dict[str, Any]] = []
    unmapped: list[dict[str, Any]] = []
    counts = {
        "total": len(indicators),
        "already_seeded": 0,
        "kept": 0,
        "dropped_no_data": 0,
        "unmapped": 0,
        "fetch_failed": 0,
    }

    # --- Phase 1: warm the presence cache in parallel (network-bound) ---
    to_fetch = [
        ind.code
        for ind in indicators
        if ind.code not in ALREADY_SEEDED
        and not (CACHE_DIR / f"{ind.code}.json").exists()
    ]
    failed_codes: set[str] = set()
    if to_fetch:
        print(f"Fetching Nepal presence for {len(to_fetch)} un-cached indicators "
              f"({FETCH_WORKERS} workers)...")
        done = 0
        with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
            for failed in pool.map(_warm_one, to_fetch):
                done += 1
                if failed is not None:
                    failed_codes.add(failed)
                if done % 100 == 0:
                    print(f"  ... {done}/{len(to_fetch)} fetched"
                          f" ({len(failed_codes)} failed so far)")
        if failed_codes:
            print(f"  {len(failed_codes)} indicators failed to fetch after retries"
                  f" — reported, not loaded. Re-run to retry just those.")
    else:
        print("All presence responses already cached — resuming from cache.")

    # --- Phase 2: curate deterministically from the cache (offline) ---
    for ind in indicators:
        if ind.code in ALREADY_SEEDED:
            counts["already_seeded"] += 1
            continue
        if not (CACHE_DIR / f"{ind.code}.json").exists():
            counts["fetch_failed"] += 1
            unmapped.append(
                {
                    "wdi_code": ind.code,
                    "name_wb": ind.name,
                    "wb_unit": ind.unit,
                    "wb_topics": " | ".join(ind.topics),
                    "unit_resolved": "",
                    "sector_resolved": "",
                    "reason": "presence fetch failed after retries",
                    "latest_year": "",
                    "latest_value": "",
                }
            )
            continue

        presence = fetch_presence(ind.code)
        has_recent = (
            presence.latest_year is not None
            and presence.latest_year >= MIN_YEAR
            and presence.latest_value is not None
        )
        if not has_recent:
            counts["dropped_no_data"] += 1
            continue

        unit = resolve_unit(ind.name, ind.unit)
        sector = resolve_sector(ind.code, ind.topics)
        if unit is None or sector is None:
            counts["unmapped"] += 1
            unmapped.append(
                {
                    "wdi_code": ind.code,
                    "name_wb": ind.name,
                    "wb_unit": ind.unit,
                    "wb_topics": " | ".join(ind.topics),
                    "unit_resolved": unit or "",
                    "sector_resolved": sector or "",
                    "reason": (
                        "unit unresolved"
                        if unit is None and sector is not None
                        else "sector unresolved"
                        if sector is None and unit is not None
                        else "unit+sector unresolved"
                    ),
                    "latest_year": presence.latest_year,
                    "latest_value": presence.latest_value,
                }
            )
            continue

        counts["kept"] += 1
        kept.append(
            {
                "code": our_code(ind.code),
                "wdi_code": ind.code,
                "name_wb": ind.name,
                "topic": sector,
                "unit_code": unit,
                "wb_topic": ind.topics[0] if ind.topics else "",
                "latest_year": presence.latest_year,
                "latest_value": presence.latest_value,
            }
        )

    kept.sort(key=lambda r: (str(r["topic"]), str(r["code"])))
    unmapped.sort(key=lambda r: str(r["wdi_code"]))
    _write_csv(KEEP_CSV, kept, ["code", "wdi_code", "name_wb", "topic",
                                "unit_code", "wb_topic", "latest_year",
                                "latest_value"])
    _write_csv(UNMAPPED_CSV, unmapped, ["wdi_code", "name_wb", "wb_unit",
                                        "wb_topics", "unit_resolved",
                                        "sector_resolved", "reason",
                                        "latest_year", "latest_value"])
    return counts


def _write_csv(path: Path, rows: list[dict[str, Any]], header: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(counts: dict[str, int]) -> None:
    considered = counts["total"] - counts["already_seeded"]
    kept = counts["kept"]
    unmapped = counts["unmapped"]
    mappable = kept + unmapped
    unmapped_pct = (100.0 * unmapped / mappable) if mappable else 0.0
    print("\n=== World Bank catalogue summary (P2B.S3a) ===")
    print(f"  indicators in WB source 2      : {counts['total']}")
    print(f"  already hand-seeded (excluded) : {counts['already_seeded']}")
    print(f"  considered                     : {considered}")
    print(f"  KEPT (has data, unit+sector ok): {kept}   -> {KEEP_CSV.relative_to(REPO_ROOT)}")
    print(f"  dropped — no recent Nepal data : {counts['dropped_no_data']}")
    print(f"  fetch failed (retry next run)  : {counts['fetch_failed']}")
    print(f"  UNMAPPED (has data, rules miss) : {unmapped}"
          f"   -> {UNMAPPED_CSV.relative_to(REPO_ROOT)}")
    print(f"  unmapped share of has-data set : {unmapped_pct:.1f}%"
          f"  ({'OK' if unmapped_pct <= 15 else 'HIGH — consider extending rules'})")
    print("=" * 48)


def run(argv: list[str] | None = None) -> int:
    configure_stdout_utf8()
    parser = argparse.ArgumentParser(description="Curate the full WB WDI catalogue (P2B.S3a).")
    parser.add_argument("--limit", type=int, default=None,
                        help="only check the first N indicators (smoke test)")
    args = parser.parse_args(argv)
    try:
        counts = build_catalogue(args.limit)
    except requests.RequestException as exc:
        print(f"FAILURE: World Bank API request failed: {exc}")
        print("  Cached codes are preserved — just re-run to resume.")
        return 1
    print_summary(counts)
    print("Done. Review the two CSVs, then proceed to P2B.S3b to load them.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
