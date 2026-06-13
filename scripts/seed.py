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


def seed_geographies(cur: Cursor) -> int:
    rows = _read_csv("geographies.csv")
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
            (f"{year}-01-01", f"{year}-12-31", str(year), year),
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
            "  topic, source_concept, preferred_source_id)"
            " VALUES (%s, %s, NULL, %s, NULL, %s, %s, %s, %s)"
            " ON CONFLICT (code) DO UPDATE SET"
            "   name_en = EXCLUDED.name_en,"
            "   definition_en = EXCLUDED.definition_en,"
            "   unit_id = EXCLUDED.unit_id,"
            "   topic = EXCLUDED.topic,"
            "   source_concept = EXCLUDED.source_concept,"
            "   preferred_source_id = EXCLUDED.preferred_source_id",
            (r["code"], name_en, definition_en, unit_id, r["topic"], wdi, source_id),
        )
        loaded += 1
    return loaded, failures


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
        seed_time_periods(cur)
        loaded, failures = seed_indicators(cur, source_id)
        conn.commit()

        counts = {}
        for table in ("units", "sources", "datasets", "geographies", "time_periods", "indicators"):
            cur.execute(f"SELECT count(*) FROM {table}")  # noqa: S608 — fixed table names
            counts[table] = _scalar(cur)

    print("Seed summary (table row counts):")
    for table, count in counts.items():
        print(f"  {table:13} {count}")
    print(f"\nIndicators loaded this run: {loaded}")

    if failures:
        print("\nWDI codes that FAILED verification (NOT loaded, NOT guessed):")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("All indicator WDI codes verified against the World Bank API.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
