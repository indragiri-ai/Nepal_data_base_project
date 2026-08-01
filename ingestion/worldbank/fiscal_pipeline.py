"""Load the VERIFIED federal fiscal headline series into the warehouse (WBF.S2).

Scope is deliberately narrow. Only the dashboard's aggregate ("headline") rows
are loaded, because only those have been checked against Nepal's own published
accounts:

    FY 2018/19  revenue     765,535.7  vs FCGO non-financing receipt 764,767.76  (0.10%)
    FY 2022/23  revenue     913,786.1  vs FCGO non-financing receipt 910,370.97  (0.38%)
    FY 2018/19  expenditure 957,980.1  vs FCGO recurrent+capital     944,351.58  (1.44%)

The dashboard's revenue CATEGORY rows (taxes, grants, other revenue,
miscellaneous receipt) are NOT loaded. They do not sum to the aggregate in any
year after FY 2017/18, and the reason is not established — a revenue-sharing
explanation fits FY 2018/19 to 0.12% but fails for FY 2022/23 by 12%. Loading
them would let a reader add four published numbers and get a fifth number that
contradicts the published total. See reference/wb-fiscal/PROVENANCE.md.

Budget and Actual are separate indicators and never mixed.

Idempotent: a value equal to the current latest observation is skipped, so
re-running loads nothing. Revisions insert under a new release and the
is_latest trigger demotes the old row — nothing is ever overwritten.

Run with `make ingest-wb-fiscal`. Options:
    --dry-run   fetch, check and report; write nothing to the database
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ingestion.common.io_utf8 import configure_stdout_utf8  # noqa: E402
from ingestion.worldbank.fiscal_acquire import (  # noqa: E402
    REQUEST_PAUSE_S,
    fetch_sheet,
    open_session,
)
from ingestion.worldbank.fiscal_layout import (  # noqa: E402
    FEDERAL_GEO_CODE,
    FEDERAL_SHEETS,
    SOURCE_UNIT_LABEL,
    UNIT_CODE,
    dashboard_year_to_period_label,
    parse_amount,
)

SEED_CSV = Path("db/seeds/indicators_fiscal.csv")
DATASET_NAME = "Nepal Fiscal Dashboard"
SOURCE_NAME = "World Bank"

# Which indicator code carries each (sheet, Type1) aggregate series.
SERIES: dict[tuple[str, str], str] = {
    ("Federal Revenue", "Actual"): "FISCAL_REVENUE_ACTUAL",
    ("Federal Revenue", "Budget"): "FISCAL_REVENUE_BUDGET",
    ("Federal Expenditure", "Actual"): "FISCAL_EXPENDITURE_ACTUAL",
    ("Federal Expenditure", "Budget"): "FISCAL_EXPENDITURE_BUDGET",
    ("Federal Financing", "Actual"): "FISCAL_FINANCING_ACTUAL",
    ("Federal Financing", "Budget"): "FISCAL_FINANCING_BUDGET",
    ("Federal Debt Stock", "Actual"): "FISCAL_DEBT_STOCK",
    ("Federal Fiscal Indicators", "Actual"): "FISCAL_NET_OPERATING_BALANCE_ACTUAL",
    ("Federal Fiscal Indicators", "Budget"): "FISCAL_NET_OPERATING_BALANCE_BUDGET",
}

# Sanity band. Nepal's federal aggregates are hundreds of thousands of NPR
# million; anything outside this is a unit error (the 1000x classic) or a
# changed source, and must stop the load rather than be published.
MIN_ABS = Decimal("100")
MAX_ABS = Decimal("5000000")


class FiscalLoadError(Exception):
    """Refuse to load rather than publish something unverified."""


@dataclass(frozen=True)
class Row:
    indicator_code: str
    period_label: str
    value: Decimal


def _scalar(cur: psycopg.Cursor[Any]) -> Any:
    row = cur.fetchone()
    return None if row is None else row[0]


def harvest() -> list[Row]:
    """Fetch every aggregate series named in SERIES."""
    session = open_session()
    time.sleep(REQUEST_PAUSE_S)
    out: list[Row] = []
    for spec in FEDERAL_SHEETS:
        for measure_type in spec.types:
            code = SERIES.get((spec.sheet, measure_type))
            if code is None:
                continue
            payload = fetch_sheet(session, spec.sheet, {"Type1": measure_type})
            rows = payload.rows
            header, body = rows[0], rows[1:]
            if not body:
                raise FiscalLoadError(
                    f"{spec.sheet} Type1={measure_type}: no rows — the sheet changed."
                )
            year_ix = header.index("Year1") if "Year1" in header else 0
            for row in body:
                value = parse_amount(row[1])
                if not (MIN_ABS <= abs(value) <= MAX_ABS):
                    raise FiscalLoadError(
                        f"{code} {row[year_ix]}: {value} is outside the sanity band "
                        f"[{MIN_ABS}, {MAX_ABS}] NPR million — unit error or changed source."
                    )
                out.append(
                    Row(
                        indicator_code=code,
                        period_label=dashboard_year_to_period_label(row[year_ix]),
                        value=value,
                    )
                )
            print(f"  {code:38s} {len(body)} years")
            time.sleep(REQUEST_PAUSE_S)
    return out


def verify_unit(session_unit_label: str) -> None:
    if session_unit_label != SOURCE_UNIT_LABEL:
        raise FiscalLoadError(
            f"source unit is now {session_unit_label!r}, expected {SOURCE_UNIT_LABEL!r}"
        )


def seed_indicators(cur: psycopg.Cursor[Any], source_id: int) -> int:
    """Upsert the curated indicator rows (rule 4: seeded from a CSV, idempotent)."""
    with SEED_CSV.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    cur.execute("SELECT code, id FROM units")
    unit_ids = {c: i for c, i in cur.fetchall()}
    unit_id = unit_ids.get(UNIT_CODE)
    if unit_id is None:
        raise FiscalLoadError(
            f"unit {UNIT_CODE} is not seeded — run `make seed` first (db/seeds/units.csv)."
        )
    for r in rows:
        cur.execute(
            "INSERT INTO indicators"
            " (code, name_en, definition_en, unit_id, topic, source_concept,"
            "  origin_source_id, preferred_source_id)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (code) DO UPDATE SET"
            "   name_en = EXCLUDED.name_en,"
            "   definition_en = EXCLUDED.definition_en,"
            "   unit_id = EXCLUDED.unit_id,"
            "   topic = EXCLUDED.topic,"
            "   source_concept = EXCLUDED.source_concept,"
            "   origin_source_id = EXCLUDED.origin_source_id,"
            "   preferred_source_id = EXCLUDED.preferred_source_id",
            (
                r["code"], r["name_en"], r["definition_en"], unit_id,
                r["topic"], r["source_concept"], source_id, source_id,
            ),
        )
    return len(rows)


def load(rows: list[Row], dry_run: bool) -> None:
    load_dotenv()
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        raise FiscalLoadError("DATABASE_URL is not set")

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM sources WHERE name_en = %s", (SOURCE_NAME,))
        source_id = _scalar(cur)
        if source_id is None:
            raise FiscalLoadError(f"source {SOURCE_NAME!r} is not seeded")
        cur.execute(
            "SELECT id FROM datasets WHERE source_id = %s AND name_en = %s",
            (source_id, DATASET_NAME),
        )
        dataset_id = _scalar(cur)
        if dataset_id is None:
            raise FiscalLoadError(
                f"dataset {DATASET_NAME!r} is not seeded — run `make seed` "
                "(db/seeds/datasets.csv)."
            )

        seeded = seed_indicators(cur, source_id)
        print(f"\nIndicators seeded/updated: {seeded}")

        cur.execute("SELECT code, id FROM indicators WHERE code = ANY(%s)",
                    (sorted({r.indicator_code for r in rows}),))
        indicator_ids = {c: i for c, i in cur.fetchall()}
        cur.execute("SELECT id FROM geographies WHERE code = %s", (FEDERAL_GEO_CODE,))
        geography_id = _scalar(cur)
        cur.execute("SELECT id FROM units WHERE code = %s", (UNIT_CODE,))
        unit_id = _scalar(cur)
        cur.execute(
            "SELECT gregorian_label, id FROM time_periods WHERE period_type = 'fiscal_year'"
        )
        period_ids = {label: pid for label, pid in cur.fetchall()}

        missing = sorted({r.period_label for r in rows} - period_ids.keys())
        if missing:
            raise FiscalLoadError(
                f"fiscal-year periods not seeded: {missing}. Run `make seed-periods-ne`."
            )

        # Current latest values, to skip unchanged rows (idempotency).
        cur.execute(
            "SELECT o.indicator_id, o.time_period_id, o.value FROM observations o"
            " WHERE o.dataset_id = %s AND o.is_latest",
            (dataset_id,),
        )
        latest = {(i, p): v for i, p, v in cur.fetchall()}

        to_insert: list[tuple[Any, ...]] = []
        unchanged = 0
        for r in rows:
            iid = indicator_ids[r.indicator_code]
            pid = period_ids[r.period_label]
            if latest.get((iid, pid)) == r.value:
                unchanged += 1
                continue
            to_insert.append((iid, geography_id, pid, dataset_id, r.value, unit_id))

        print(f"To load: {len(to_insert)}   unchanged (skipped): {unchanged}")
        if dry_run:
            print("\nDRY RUN — nothing written.")
            conn.rollback()
            return
        if not to_insert:
            print("Nothing to load; the warehouse already matches the source.")
            return

        cur.execute(
            "INSERT INTO releases (dataset_id, release_date)"
            " VALUES (%s, CURRENT_DATE) RETURNING id",
            (dataset_id,),
        )
        release_id = _scalar(cur)
        cur.executemany(
            "INSERT INTO observations"
            " (indicator_id, geography_id, time_period_id, dataset_id,"
            "  release_id, value, unit_id, status)"
            " VALUES (%s, %s, %s, %s, " + str(release_id) + ", %s, %s, 'final')",
            to_insert,
        )
        conn.commit()
        print(f"Loaded {len(to_insert)} observations under release {release_id}.")


def main() -> None:
    configure_stdout_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("Harvesting the verified federal headline series:")
    rows = harvest()
    print(f"\nHarvested {len(rows)} observations.")
    load(rows, args.dry_run)


if __name__ == "__main__":
    main()
