"""Seed reference data (P1.S6).

Loads the curated reference data the pipelines depend on, idempotently — running
it twice never creates duplicates (every table is upserted on its natural key):

  - units            from db/seeds/units.csv
  - sources          from db/seeds/sources.csv
  - datasets         from db/seeds/datasets.csv
  - geographies      from db/seeds/geographies.csv
  - time_periods     calendar years 1960-2030, generated here
  - indicators       from db/seeds/indicators.csv, with name_en/definition_en
                     fetched from the World Bank metadata API and each WDI code
                     verified to exist (failures are reported, never guessed —
                     Prime Directive 7). name_ne is left NULL: TODO Phase 3
                     translation review.
  - indicators       from db/seeds/indicators_wb_full.csv — the full curated WDI
                     catalogue (P2B.S3a/b), same verified-metadata rule, read
                     from WB's source-2 listing in one request. Disjoint from
                     indicators.csv: the hand-curated 20 keep their own codes.

Run with `make seed`.
"""

from __future__ import annotations

import os
import sys
from csv import DictReader
from pathlib import Path
from typing import Any

import psycopg
import requests
from dotenv import load_dotenv

# Make the repo root importable when run as `python scripts/seed.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingestion.common.fiscal_periods import year_sort_key  # noqa: E402
from scripts.wb_catalog import fetch_indicator_list  # noqa: E402

SEEDS_DIR = Path("db/seeds")
WB_INDICATOR_META = "https://api.worldbank.org/v2/indicator/{code}"
FIRST_YEAR = 1960
LAST_YEAR = 2030

Cursor = psycopg.Cursor[Any]


def _read_csv(name: str) -> list[dict[str, str]]:
    with (SEEDS_DIR / name).open(encoding="utf-8", newline="") as fh:
        return list(DictReader(fh))


def _none_if_blank(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _scalar(cur: Cursor) -> Any:
    row = cur.fetchone()
    return None if row is None else row[0]


def seed_units(cur: Cursor) -> int:
    rows = _read_csv("units.csv")
    for r in rows:
        cur.execute(
            "INSERT INTO units (code, name_en, name_ne, notes)"
            " VALUES (%s, %s, %s, %s)"
            " ON CONFLICT (code) DO UPDATE SET"
            "   name_en = EXCLUDED.name_en,"
            "   name_ne = EXCLUDED.name_ne,"
            "   notes = EXCLUDED.notes",
            (r["code"], r["name_en"], _none_if_blank(r["name_ne"]), _none_if_blank(r["notes"])),
        )
    return len(rows)


def seed_sources(cur: Cursor) -> int:
    rows = _read_csv("sources.csv")
    for r in rows:
        cur.execute(
            "INSERT INTO sources (name_en, name_ne, type, url, default_license, notes)"
            " VALUES (%s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (name_en) DO UPDATE SET"
            "   name_ne = EXCLUDED.name_ne,"
            "   type = EXCLUDED.type,"
            "   url = EXCLUDED.url,"
            "   default_license = EXCLUDED.default_license,"
            "   notes = EXCLUDED.notes",
            (
                r["name_en"],
                _none_if_blank(r["name_ne"]),
                r["type"],
                _none_if_blank(r["url"]),
                _none_if_blank(r["default_license"]),
                _none_if_blank(r["notes"]),
            ),
        )
    return len(rows)


def seed_datasets(cur: Cursor) -> int:
    rows = _read_csv("datasets.csv")
    for r in rows:
        cur.execute("SELECT id FROM sources WHERE name_en = %s", (r["source_name"],))
        source_id = _scalar(cur)
        if source_id is None:
            raise SystemExit(f"dataset references unknown source: {r['source_name']}")
        cur.execute(
            "INSERT INTO datasets"
            " (source_id, name_en, name_ne, license, update_frequency,"
            "  access_method, documentation_url)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (source_id, name_en) DO UPDATE SET"
            "   license = EXCLUDED.license,"
            "   update_frequency = EXCLUDED.update_frequency,"
            "   access_method = EXCLUDED.access_method,"
            "   documentation_url = EXCLUDED.documentation_url",
            (
                source_id,
                r["name_en"],
                _none_if_blank(r["name_ne"]),
                _none_if_blank(r["license"]),
                _none_if_blank(r["update_frequency"]),
                r["access_method"],
                _none_if_blank(r["documentation_url"]),
            ),
        )
    return len(rows)


def seed_geographies(cur: Cursor, filename: str = "geographies.csv") -> int:
    """Places, current or historical, from one curated file.

    `geographies_old.csv` holds the pre-2015 structure — 5 development regions
    and 75 districts — which lives alongside the current one rather than
    replacing it (blueprint §5.2: data is stored against the boundaries it was
    published in). Seed it AFTER the current file: its regions hang off the
    country row, which that file creates.
    """
    rows = _read_csv(filename)
    for r in rows:
        parent_id = None
        parent_code = _none_if_blank(r.get("parent_code"))
        if parent_code is not None:
            cur.execute("SELECT id FROM geographies WHERE code = %s", (parent_code,))
            parent_id = _scalar(cur)
        cur.execute(
            "INSERT INTO geographies"
            " (code, name_en, name_ne, level, parent_id, valid_from, valid_to, geometry_ref)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (code) DO UPDATE SET"
            "   name_en = EXCLUDED.name_en,"
            "   name_ne = EXCLUDED.name_ne,"
            "   level = EXCLUDED.level,"
            "   parent_id = EXCLUDED.parent_id,"
            "   valid_from = EXCLUDED.valid_from,"
            "   valid_to = EXCLUDED.valid_to,"
            "   geometry_ref = EXCLUDED.geometry_ref",
            (
                r["code"],
                r["name_en"],
                _none_if_blank(r["name_ne"]),
                r["level"],
                parent_id,
                _none_if_blank(r.get("valid_from")),
                _none_if_blank(r.get("valid_to")),
                _none_if_blank(r.get("geometry_ref")),
            ),
        )
    return len(rows)


def _geography_id(cur: Cursor, code: str) -> int:
    """A geography id, or a loud failure. A crosswalk that quietly skips a row
    it cannot resolve is worse than one that refuses to load."""
    cur.execute("SELECT id FROM geographies WHERE code = %s", (code,))
    found = _scalar(cur)
    if found is None:
        raise SystemExit(f"FAILURE: crosswalk names geography {code!r}, which is not seeded")
    return int(found)


def seed_geography_crosswalk(cur: Cursor) -> int:
    """Pre-2015 district -> current district, for comparison across the break.

    Only districts whose boundary survived unchanged appear here, with the whole
    share. Nawalparasi and Rukum were split in 2015 and nobody has published how
    to divide their earlier records, so they are absent on purpose — their data
    stays at the old district and is reported as such.
    """
    rows = _read_csv("geography_crosswalk.csv")
    for r in rows:
        cur.execute(
            "INSERT INTO geography_crosswalk"
            " (old_geography_id, new_geography_id, allocation_share, method, note)"
            " VALUES (%s, %s, %s, %s, %s)"
            " ON CONFLICT (old_geography_id, new_geography_id) DO UPDATE SET"
            "   allocation_share = EXCLUDED.allocation_share,"
            "   method = EXCLUDED.method,"
            "   note = EXCLUDED.note",
            (
                _geography_id(cur, r["old_code"]),
                _geography_id(cur, r["new_code"]),
                r["allocation_share"],
                r["method"],
                _none_if_blank(r.get("note")),
            ),
        )
    return len(rows)


def seed_bipad_geography_crosswalk(cur: Cursor) -> int:
    """BIPAD's own place ids -> our P-codes.

    Built from evidence by `ingestion/bipad/draft_crosswalk.py`; `evidence`
    records what resolved each row, so a reader can tell a measured match from
    a reviewed judgement.
    """
    rows = _read_csv("bipad_geography_crosswalk.csv")
    for r in rows:
        cur.execute(
            "INSERT INTO bipad_geography_crosswalk"
            " (bipad_level, bipad_id, bipad_code, bipad_title_en, geography_id, evidence)"
            " VALUES (%s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (bipad_level, bipad_id) DO UPDATE SET"
            "   bipad_code = EXCLUDED.bipad_code,"
            "   bipad_title_en = EXCLUDED.bipad_title_en,"
            "   geography_id = EXCLUDED.geography_id,"
            "   evidence = EXCLUDED.evidence",
            (
                r["bipad_level"],
                int(r["bipad_id"]),
                _none_if_blank(r.get("bipad_code")),
                r["bipad_title_en"],
                _geography_id(cur, r["geography_code"]),
                r["evidence"],
            ),
        )
    return len(rows)


def seed_time_periods(cur: Cursor) -> int:
    count = 0
    for year in range(FIRST_YEAR, LAST_YEAR + 1):
        cur.execute(
            "INSERT INTO time_periods"
            " (period_type, gregorian_start, gregorian_end, bs_label, gregorian_label, sort_key)"
            " VALUES ('year', %s, %s, NULL, %s, %s)"
            " ON CONFLICT (period_type, gregorian_start, gregorian_end) DO UPDATE SET"
            "   gregorian_label = EXCLUDED.gregorian_label,"
            "   sort_key = EXCLUDED.sort_key",
            # sort_key is the date-based YYYYMMDD scheme (docs/decisions/0002) so
            # calendar years and fiscal years share one monotonic timeline.
            (f"{year}-01-01", f"{year}-12-31", str(year), year_sort_key(year)),
        )
        count += 1
    return count


def fetch_indicator_meta(wdi_code: str) -> tuple[str, str] | None:
    """Return (name_en, definition_en) from the World Bank API, or None if the
    code does not exist / cannot be verified."""
    try:
        resp = requests.get(
            WB_INDICATOR_META.format(code=wdi_code), params={"format": "json"}, timeout=30
        )
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    payload = resp.json()
    if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
        return None
    item = payload[1][0]
    name = item.get("name")
    if not name:
        return None
    return name, item.get("sourceNote") or ""


def seed_indicators(cur: Cursor, source_id: int) -> tuple[int, list[str]]:
    rows = _read_csv("indicators.csv")
    cur.execute("SELECT code, id FROM units")
    unit_ids = {code: uid for code, uid in cur.fetchall()}
    loaded = 0
    failures: list[str] = []
    for r in rows:
        wdi = r["wdi_code"]
        unit_id = unit_ids.get(r["unit_code"])
        if unit_id is None:
            failures.append(f"{r['code']}: unknown unit '{r['unit_code']}'")
            continue
        meta = fetch_indicator_meta(wdi)
        if meta is None:
            failures.append(f"{r['code']}: WDI code '{wdi}' did not verify against the API")
            continue
        name_en, definition_en = meta
        cur.execute(
            "INSERT INTO indicators"
            " (code, name_en, name_ne, definition_en, definition_ne, unit_id,"
            "  topic, source_concept, origin_source_id, preferred_source_id)"
            " VALUES (%s, %s, NULL, %s, NULL, %s, %s, %s, %s, %s)"
            " ON CONFLICT (code) DO UPDATE SET"
            "   name_en = EXCLUDED.name_en,"
            "   definition_en = EXCLUDED.definition_en,"
            "   unit_id = EXCLUDED.unit_id,"
            "   topic = EXCLUDED.topic,"
            "   source_concept = EXCLUDED.source_concept,"
            "   origin_source_id = EXCLUDED.origin_source_id,"
            # preferred is reset to the origin here; seed_headline_sources() then
            # repoints the collision alternatives (idempotent, runs after).
            "   preferred_source_id = EXCLUDED.preferred_source_id",
            (r["code"], name_en, definition_en, unit_id, r["topic"], wdi, source_id, source_id),
        )
        loaded += 1
    return loaded, failures


def seed_indicators_wb_full(cur: Cursor, source_id: int) -> tuple[int, list[str]]:
    """Seed the full curated WDI catalogue from db/seeds/indicators_wb_full.csv
    (P2B.S3b).

    Same verified-metadata rule as the hand-curated 20: name_en and definition_en
    come from World Bank's own metadata, and a code that does not appear in the
    live source-2 listing is REPORTED, never guessed. The difference is where the
    metadata is read from — WB's source-2 indicator listing carries `name` and
    `sourceNote` for every indicator in one response, so this verifies 1,336
    codes with a single request instead of hammering the API 1,336 times.

    Writes are batched with executemany: Supabase's free tier drops connections
    under sustained row-by-row traffic (CLAUDE.md rule 8).
    """
    rows = _read_csv("indicators_wb_full.csv")
    if not rows:
        return 0, []

    live = {ind.code: ind for ind in fetch_indicator_list()}
    cur.execute("SELECT code, id FROM units")
    unit_ids = {code: uid for code, uid in cur.fetchall()}

    params: list[tuple[Any, ...]] = []
    failures: list[str] = []
    for r in rows:
        wdi = r["wdi_code"]
        unit_id = unit_ids.get(r["unit_code"])
        if unit_id is None:
            failures.append(f"{r['code']}: unknown unit '{r['unit_code']}' — run seed_units first")
            continue
        meta = live.get(wdi)
        if meta is None:
            failures.append(f"{r['code']}: WDI code '{wdi}' is not in WB's live source-2 listing")
            continue
        params.append(
            (r["code"], meta.name, meta.definition, unit_id, r["topic"], wdi,
             source_id, source_id)
        )

    cur.executemany(
        "INSERT INTO indicators"
        " (code, name_en, name_ne, definition_en, definition_ne, unit_id,"
        "  topic, source_concept, origin_source_id, preferred_source_id)"
        " VALUES (%s, %s, NULL, %s, NULL, %s, %s, %s, %s, %s)"
        " ON CONFLICT (code) DO UPDATE SET"
        "   name_en = EXCLUDED.name_en,"
        "   definition_en = EXCLUDED.definition_en,"
        "   unit_id = EXCLUDED.unit_id,"
        "   topic = EXCLUDED.topic,"
        "   source_concept = EXCLUDED.source_concept,"
        "   origin_source_id = EXCLUDED.origin_source_id,"
        "   preferred_source_id = EXCLUDED.preferred_source_id",
        params,
    )
    return len(params), failures


def seed_headline_sources(cur: Cursor) -> tuple[int, list[str]]:
    """Repoint preferred_source_id for colliding concepts to the HEADLINE source
    (P2B.S4 / decision 0005), from db/seeds/headline_sources.csv.

    Runs AFTER the indicator seeders, which reset preferred_source_id to each
    indicator's own (origin) source — this step then demotes the alternatives so
    the census/NRB headline wins. origin_source_id is untouched, so the WB
    pipeline keeps refreshing the demoted series. A missing indicator or source
    is REPORTED, never guessed (rule #1).
    """
    rows = _read_csv("headline_sources.csv")
    if not rows:
        return 0, []
    cur.execute("SELECT name_en, id FROM sources")
    source_ids = {name: sid for name, sid in cur.fetchall()}
    applied = 0
    failures: list[str] = []
    for r in rows:
        code = r["alternative_code"]
        headline = r["headline_source"]
        headline_id = source_ids.get(headline)
        if headline_id is None:
            failures.append(f"{code}: unknown headline source '{headline}'")
            continue
        cur.execute(
            "UPDATE indicators SET preferred_source_id = %s WHERE code = %s",
            (headline_id, code),
        )
        if cur.rowcount == 0:
            failures.append(f"{code}: indicator not found — cannot set headline source")
            continue
        applied += 1
    return applied, failures


def main() -> int:
    load_dotenv()
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print("FAILURE: DATABASE_URL is empty. Fill in .env (see .env.example).")
        return 1

    with psycopg.connect(url) as conn, conn.cursor() as cur:
        seed_units(cur)
        seed_sources(cur)
        cur.execute("SELECT id FROM sources WHERE name_en = %s", ("World Bank",))
        source_id = _scalar(cur)
        seed_datasets(cur)
        seed_geographies(cur)
        seed_geographies(cur, "geographies_old.csv")
        seed_geography_crosswalk(cur)
        seed_bipad_geography_crosswalk(cur)
        seed_time_periods(cur)
        loaded, failures = seed_indicators(cur, source_id)
        wb_loaded, wb_failures = seed_indicators_wb_full(cur, source_id)
        failures.extend(wb_failures)
        # Repoint headline sources LAST — after the seeders reset preferred to origin.
        headline_applied, headline_failures = seed_headline_sources(cur)
        failures.extend(headline_failures)
        conn.commit()

        counts = {}
        for table in (
            "units",
            "sources",
            "datasets",
            "geographies",
            "geography_crosswalk",
            "bipad_geography_crosswalk",
            "time_periods",
            "indicators",
        ):
            cur.execute(f"SELECT count(*) FROM {table}")  # noqa: S608 — fixed table names
            counts[table] = _scalar(cur)

    print("Seed summary (table row counts):")
    for table, count in counts.items():
        print(f"  {table:13} {count}")
    print(f"\nIndicators loaded this run: {loaded} hand-curated + {wb_loaded} WB full catalogue")
    print(f"Headline sources repointed (decision 0005): {headline_applied}")

    if failures:
        print("\nWDI codes that FAILED verification (NOT loaded, NOT guessed):")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("All indicator WDI codes verified against the World Bank API.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
