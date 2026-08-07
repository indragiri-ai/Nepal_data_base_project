"""Load Kalimati daily wholesale prices into the warehouse (ODN.S2, part 2).

WHAT IS STORED
--------------
Two series per commodity-day — the day's LOW and HIGH, both the market board's
own published figures — under `breakdowns = {"commodity": <name>}`, in NPR per
kilogram, for the 25-commodity basket in `db/seeds/kalimati_basket.csv`.

The source's third column, "Average", is deliberately NOT stored. It is exactly
(min + max) / 2 in 100.00% of 5,000 rows sampled across the whole series, and
it disagrees with the market board's own published average (which sits nearer
the day's high). Storing it would spend a third of the space on arithmetic and
publish a misleading label; the API derives a MIDPOINT for display instead.

GEOGRAPHY: the market, not the country
--------------------------------------
Filed under Kathmandu Metropolitan City (`NP0327101`), where the Kalimati
market physically is — not under Nepal. These are one market's wholesale
prices; filing them nationally would assert they are Nepal's prices, which the
source does not claim. The commodity basket travels from all over Nepal and
India, so the market is a national benchmark, but that is a thing to say in
words, not to encode as a geography.

Run with `make ingest-kalimati`. Options:
    --dry-run    do everything, write nothing, print the review report
    --basket N   load only the first N commodities of the basket (rehearsal)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ingestion.common.io_utf8 import configure_stdout_utf8  # noqa: E402
from ingestion.opendatanepal.kalimati_acquire import (  # noqa: E402
    KalimatiError,
    PriceRow,
    acquire,
)

BASKET_CSV = Path("db/seeds/kalimati_basket.csv")
SEED_CSV = Path("db/seeds/indicators_kalimati.csv")

SOURCE_NAME = "Kalimati Fruits and Vegetable Market Development Board"
SOURCE_URL = "https://kalimatimarket.gov.np/"
DATASET_NAME = "Kalimati Tarkari Market Dataset"
DATASET_URL = "https://opendatanepal.com/dataset/kalimati-tarkari-dataset"
DATASET_LICENSE = "CC BY 4.0 (cc-by, as stated by Open Data Nepal)"
GEO_CODE = "NP0327101"  # Kathmandu Metropolitan City — where the market is
UNIT_CODE = "NPR_PER_KG"

MIN_INDICATOR = "KALIMATI_PRICE_MIN"
MAX_INDICATOR = "KALIMATI_PRICE_MAX"

BATCH = 5000  # Supabase drops connections under sustained row-by-row writes


def read_basket(limit: int | None = None) -> list[str]:
    """The curated basket, from its reviewable CSV (rule 4)."""
    if not BASKET_CSV.exists():
        raise KalimatiError(f"{BASKET_CSV} is missing — run `make kalimati-acquire` first.")
    with BASKET_CSV.open(encoding="utf-8", newline="") as fh:
        names = [row["commodity"].strip() for row in csv.DictReader(fh) if row["commodity"].strip()]
    if not names:
        raise KalimatiError(f"{BASKET_CSV} lists no commodities.")
    return names[:limit] if limit else names


def _scalar(cur: psycopg.Cursor[Any]) -> Any:
    row = cur.fetchone()
    return None if row is None else row[0]


def ensure_source_and_dataset(cur: psycopg.Cursor[Any]) -> int:
    """The agency is the SOURCE; Open Data Nepal is only how we reached it.

    Recording the aggregator as the source would credit a distributor for a
    government market board's work and break the trail back to the office that
    can answer questions about the numbers.
    """
    cur.execute(
        "INSERT INTO sources (name_en, type, url, default_license, notes)"
        " VALUES (%s, 'ministry', %s, %s, %s)"
        " ON CONFLICT (name_en) DO UPDATE SET url = EXCLUDED.url,"
        "   default_license = EXCLUDED.default_license, notes = EXCLUDED.notes"
        " RETURNING id",
        (
            SOURCE_NAME,
            SOURCE_URL,
            DATASET_LICENSE,
            "A government market development board under the Ministry of Agriculture "
            "and Livestock Development. 'ministry' is the closest value the sources.type "
            "CHECK allows; the board is not itself a ministry.",
        ),
    )
    source_id = _scalar(cur)

    cur.execute(
        "INSERT INTO datasets (source_id, name_en, license, update_frequency,"
        "  access_method, documentation_url)"
        " VALUES (%s, %s, %s, %s, 'api', %s)"
        " ON CONFLICT (source_id, name_en) DO UPDATE SET license = EXCLUDED.license,"
        "   update_frequency = EXCLUDED.update_frequency,"
        "   documentation_url = EXCLUDED.documentation_url"
        " RETURNING id",
        (
            source_id,
            DATASET_NAME,
            DATASET_LICENSE,
            "daily while published; the series ends 2022-04-18",
            DATASET_URL,
        ),
    )
    return int(_scalar(cur))


def seed_indicators(cur: psycopg.Cursor[Any], source_id: int, unit_id: int) -> int:
    with SEED_CSV.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        if r["unit"] != UNIT_CODE:
            raise KalimatiError(f"{r['code']}: seed unit {r['unit']!r} != {UNIT_CODE!r}")
        cur.execute(
            "INSERT INTO indicators"
            " (code, name_en, definition_en, unit_id, topic, source_concept,"
            "  origin_source_id, preferred_source_id)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (code) DO UPDATE SET"
            "   name_en = EXCLUDED.name_en, definition_en = EXCLUDED.definition_en,"
            "   unit_id = EXCLUDED.unit_id, topic = EXCLUDED.topic,"
            "   source_concept = EXCLUDED.source_concept,"
            "   origin_source_id = EXCLUDED.origin_source_id,"
            "   preferred_source_id = EXCLUDED.preferred_source_id",
            (r["code"], r["name_en"], r["definition_en"], unit_id, r["topic"],
             r["source_concept"], source_id, source_id),
        )
    return len(rows)


def ensure_day_periods(cur: psycopg.Cursor[Any], days: set[date]) -> dict[date, int]:
    """Create period rows for the days the data actually has, and no others.

    Pre-seeding a decade of calendar days would be ~3,600 rows most of which no
    source would ever reference. `sort_key` is the date as YYYYMMDD, the
    date-based scheme from decision 0002, so a day sorts correctly against
    every other period type on one timeline.
    """
    cur.execute(
        "SELECT gregorian_start, id FROM time_periods WHERE period_type = 'day'"
    )
    existing: dict[date, int] = {d: i for d, i in cur.fetchall()}
    missing = sorted(days - set(existing))
    if missing:
        cur.executemany(
            "INSERT INTO time_periods"
            " (period_type, gregorian_start, gregorian_end, gregorian_label, sort_key)"
            " VALUES ('day', %s, %s, %s, %s)"
            " ON CONFLICT (period_type, gregorian_start, gregorian_end) DO NOTHING",
            [(d, d, d.isoformat(), int(d.strftime("%Y%m%d"))) for d in missing],
        )
        cur.execute(
            "SELECT gregorian_start, id FROM time_periods WHERE period_type = 'day'"
        )
        existing = {d: i for d, i in cur.fetchall()}
    print(f"Day periods: {len(existing):,} present ({len(missing):,} created)")
    return existing


def deduplicate(rows: list[PriceRow]) -> tuple[list[PriceRow], int, list[str]]:
    """One row per commodity-day, preferring the LATER resource.

    The two resources overlap: resource 1 runs to 2021-05-13 and resource 2
    starts 2021-01-05, so about four months of trading days appear in both.
    Loading them unfiltered means offering the warehouse the same cell twice,
    which the `observations_unique_per_release` constraint rejects — as it
    should; the alternative is a silently double-counted price.

    `rows` arrives in resource order, so a later row overwrites an earlier one
    and the newer publication wins — the tie-break the step file specifies.
    Conflicts are COUNTED and returned rather than swallowed: two published
    numbers for one commodity-day is a fact about the source that a reader is
    entitled to know, even when the newer one is preferred.
    """
    chosen: dict[tuple[str, date], PriceRow] = {}
    overlaps = 0
    conflicts: list[str] = []
    for row in rows:
        key = (row.commodity, row.day)
        previous = chosen.get(key)
        if previous is not None:
            overlaps += 1
            if (previous.minimum, previous.maximum) != (row.minimum, row.maximum):
                conflicts.append(
                    f"{row.commodity} on {row.day}: "
                    f"{previous.minimum}-{previous.maximum} then "
                    f"{row.minimum}-{row.maximum} (the later one is kept)"
                )
        chosen[key] = row
    return list(chosen.values()), overlaps, conflicts


def load(rows: list[PriceRow], basket: list[str], dry_run: bool) -> int:
    load_dotenv()
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        raise KalimatiError("DATABASE_URL is not set")

    wanted = set(basket)
    kg_basket = [r for r in rows if r.unit.lower() == "kg" and r.commodity in wanted]
    print(f"\nRows in the basket, priced per Kg: {len(kg_basket):,}")
    if not kg_basket:
        raise KalimatiError("nothing to load — the basket matched no rows.")

    kg_basket, overlaps, conflicts = deduplicate(kg_basket)
    print(f"After de-duplicating the resources' overlap: {len(kg_basket):,} "
          f"commodity-days ({overlaps:,} duplicate rows dropped)")
    if conflicts:
        print(f"  {len(conflicts):,} of those disagreed between the two resources; "
              "the later publication is kept. First few:")
        for line in conflicts[:5]:
            print(f"    {line}")
    else:
        print("  every duplicated commodity-day agreed exactly between the two "
              "resources.")

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM units WHERE code = %s", (UNIT_CODE,))
        unit_id = _scalar(cur)
        if unit_id is None:
            raise KalimatiError(
                f"unit {UNIT_CODE} is not seeded — run `make seed` (db/seeds/units.csv)."
            )
        cur.execute("SELECT id FROM geographies WHERE code = %s", (GEO_CODE,))
        geo_id = _scalar(cur)
        if geo_id is None:
            raise KalimatiError(f"geography {GEO_CODE} is not seeded.")

        dataset_id = ensure_source_and_dataset(cur)
        cur.execute("SELECT source_id FROM datasets WHERE id = %s", (dataset_id,))
        source_id = int(_scalar(cur))
        print(f"Indicators seeded/updated: {seed_indicators(cur, source_id, unit_id)}")

        cur.execute(
            "SELECT code, id FROM indicators WHERE code = ANY(%s)",
            ([MIN_INDICATOR, MAX_INDICATOR],),
        )
        indicator_ids = {c: i for c, i in cur.fetchall()}

        periods = ensure_day_periods(cur, {r.day for r in kg_basket})

        # Existing latest values, so a re-run loads nothing.
        cur.execute(
            "SELECT o.indicator_id, o.time_period_id, o.breakdowns->>'commodity', o.value"
            " FROM observations o WHERE o.dataset_id = %s AND o.is_latest",
            (dataset_id,),
        )
        latest: dict[tuple[int, int, str], Decimal] = {
            (iid, pid, name): value for iid, pid, name, value in cur.fetchall()
        }
        print(f"Already loaded (latest): {len(latest):,}")

        to_insert: list[tuple[Any, ...]] = []
        unchanged = 0
        for row in kg_basket:
            period_id = periods[row.day]
            breakdowns = json.dumps({"commodity": row.commodity})
            for code, value in (
                (MIN_INDICATOR, row.minimum),
                (MAX_INDICATOR, row.maximum),
            ):
                iid = indicator_ids[code]
                if latest.get((iid, period_id, row.commodity)) == value:
                    unchanged += 1
                    continue
                to_insert.append((iid, geo_id, period_id, dataset_id, value, unit_id, breakdowns))

        print(f"To load: {len(to_insert):,}   unchanged (skipped): {unchanged:,}")
        if dry_run:
            print("\nDRY RUN — nothing written.")
            conn.rollback()
            return 0
        if not to_insert:
            print("Nothing to load; the warehouse already matches the source.")
            return 0

        cur.execute(
            "INSERT INTO releases (dataset_id, release_date)"
            " VALUES (%s, CURRENT_DATE) RETURNING id",
            (dataset_id,),
        )
        release_id = _scalar(cur)
        for start in range(0, len(to_insert), BATCH):
            chunk = to_insert[start : start + BATCH]
            cur.executemany(
                "INSERT INTO observations"
                " (indicator_id, geography_id, time_period_id, dataset_id,"
                "  release_id, value, unit_id, breakdowns, status)"
                " VALUES (%s, %s, %s, %s, " + str(release_id) + ", %s, %s, %s, 'final')",
                chunk,
            )
            conn.commit()
            print(f"  committed {min(start + BATCH, len(to_insert)):>7,} / {len(to_insert):,}")
        print(f"Loaded {len(to_insert):,} observations under release {release_id}.")
        return len(to_insert)


def main() -> int:
    configure_stdout_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--basket", type=int, default=None)
    args = parser.parse_args()

    basket = read_basket(args.basket)
    print(f"Basket: {len(basket)} commodities from {BASKET_CSV}")

    rows = acquire(limit_pages=None, write_raw=False)
    load(rows, basket, args.dry_run)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KalimatiError as exc:
        print(f"\nLOAD FAILED: {exc}", file=sys.stderr)
        sys.exit(2)
