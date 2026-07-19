"""Seed the Census 2021 indicators (NSO onboarding).

Loads db/seeds/indicators_census.csv — generated from
ingestion.nso.census_layout.REGISTRY, the single source of truth (a test locks
them in sync) — into `indicators`, idempotently (upsert on code).

There is no NSO metadata API to verify names against: names and definitions
were written by hand from the census results portal itself (runbook: reference
data is curated by a human, never invented).

The NSO source row, census dataset row, and RATIO/PER_KM2 units ride along with
the normal `make seed`. Run with `make seed-census` (after `make seed`).
"""

from __future__ import annotations

import os
import sys
from csv import DictReader
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv

# Make the repo root importable when run as `python scripts/seed_census.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingestion.common.io_utf8 import configure_stdout_utf8  # noqa: E402

CSV_PATH = Path("db/seeds/indicators_census.csv")
SOURCE_NAME = "National Statistics Office"

Cursor = psycopg.Cursor[Any]


def seed_census_indicators(cur: Cursor) -> tuple[int, list[str]]:
    with CSV_PATH.open(encoding="utf-8", newline="") as fh:
        rows = list(DictReader(fh))

    cur.execute("SELECT code, id FROM units")
    unit_ids = {code: uid for code, uid in cur.fetchall()}
    cur.execute("SELECT id FROM sources WHERE name_en = %s", (SOURCE_NAME,))
    found = cur.fetchone()
    if found is None:
        raise SystemExit(
            f"source '{SOURCE_NAME}' not found — run `make seed` first (sources.csv)"
        )
    source_id = found[0]

    loaded = 0
    failures: list[str] = []
    for r in rows:
        unit_id = unit_ids.get(r["unit_code"])
        if unit_id is None:
            failures.append(f"{r['code']}: unknown unit '{r['unit_code']}' — run `make seed`")
            continue
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
            (
                r["code"], r["name_en"], r["definition_en"],
                unit_id, r["topic"], r["source_concept"], source_id,
            ),
        )
        loaded += 1
    return loaded, failures


def main() -> None:
    configure_stdout_utf8()
    load_dotenv()
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        raise SystemExit("DATABASE_URL is empty — fill it in .env first")

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        loaded, failures = seed_census_indicators(cur)
        if failures:
            conn.rollback()
            print("FAILED — nothing was written:")
            for f in failures:
                print("  -", f)
            raise SystemExit(1)
        conn.commit()
        cur.execute("SELECT count(*) FROM indicators WHERE code LIKE 'CENSUS_%'")
        row = cur.fetchone()
        total = row[0] if row is not None else 0
    print(f"Seeded {loaded} census indicators (now {total} in the database). Idempotent.")


if __name__ == "__main__":
    main()
