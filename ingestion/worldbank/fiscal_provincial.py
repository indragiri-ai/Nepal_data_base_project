"""Load provincial fiscal data for all seven provinces (WBF.S2, provincial half).

WHAT IS STORED, AND WHY IT IS TRUSTWORTHY
-----------------------------------------
Each province-year-category value is the source's OWN published figure, stored
under `breakdowns = {"category": ...}`. Nothing is invented.

A per-province TOTAL is derived (the sum of that province's categories) and
stored as the headline row (`breakdowns = {}`) so the choropleth has something
to draw. Deriving a total is only safe because it is gated:

    for every sheet, type, year and category:
        sum over the seven provinces  ==  the source's own all-provinces figure

That all-provinces figure is published by the same sheet with no province
filter, so the check is against the source, not against ourselves. It passed
exactly on the spike (FY2024 taxes: the seven provinces sum to 84,969.36, the
published all-provinces value, to the last decimal). If it ever fails, a
province is missing or a category was dropped, and the load stops.

This is deliberately different from the FEDERAL treatment, where category rows
are NOT published: there the source publishes its own aggregate AND its parts,
and they disagree, so summing the parts would contradict the source. Here the
source publishes no provincial aggregate to contradict.

Run with `make ingest-wb-fiscal-provincial`. Options:
    --dry-run   harvest and check, write nothing
    --years N   only the most recent N fiscal years (testing)
"""

from __future__ import annotations

import argparse
import json
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
    FIRST_DASHBOARD_YEAR,
    LAST_DASHBOARD_YEAR,
    PROVINCE_CODES,
    dashboard_year_to_period_label,
    parse_amount,
)
from ingestion.worldbank.fiscal_pipeline import (  # noqa: E402
    DATASET_NAME,
    MAX_ABS,
    SEED_CSV,
    SOURCE_NAME,
    FiscalLoadError,
    _scalar,
    seed_indicators,
)

# (sheet, indicator prefix). Financing and Fiscal Indicators are left for a
# later pass — these three carry the story and keep the harvest inside ~6 min.
SHEETS: tuple[tuple[str, str], ...] = (
    ("Provincial Revenue", "FISCAL_PROV_REVENUE"),
    ("Provincial Expenditure", "FISCAL_PROV_EXPENDITURE"),
    ("Provincial Grants", "FISCAL_PROV_GRANTS"),
)
TYPES = ("Actual", "Budget")

# The all-provinces cross-check tolerance. The source publishes one decimal, so
# rounding over seven provinces can move the last place; more than this is a
# missing province or category.
SUM_TOLERANCE = Decimal("1.0")


@dataclass(frozen=True)
class ProvRow:
    indicator_code: str
    geo_code: str
    period_label: str
    category: str  # "" for the derived provincial total
    value: Decimal


def _category_column(header: list[str]) -> int:
    for name in ("Group2", "Group2 (Prov!Grant)"):
        if name in header:
            return header.index(name)
    raise FiscalLoadError(f"no category column in header {header}")


def _rows(session: Any, sheet: str, filters: dict[str, str]) -> list[tuple[str, Decimal]]:
    """(category, value) pairs for one slice."""
    payload = fetch_sheet(session, sheet, filters)
    rows = payload.rows
    time.sleep(REQUEST_PAUSE_S)
    if len(rows) < 2:
        return []
    cat_ix = _category_column(rows[0])
    out: list[tuple[str, Decimal]] = []
    for r in rows[1:]:
        value = parse_amount(r[1])
        if abs(value) > MAX_ABS:
            raise FiscalLoadError(
                f"{sheet} {filters}: {value} exceeds the sanity ceiling {MAX_ABS} "
                "NPR million — unit error or changed source."
            )
        out.append((r[cat_ix], value))
    return out


def harvest(years: list[str]) -> tuple[list[ProvRow], list[str]]:
    """Returns (rows, problems). Problems are cross-check failures."""
    session = open_session()
    time.sleep(REQUEST_PAUSE_S)

    rows: list[ProvRow] = []
    problems: list[str] = []

    for sheet, prefix in SHEETS:
        for measure_type in TYPES:
            code = f"{prefix}_{measure_type.upper()}"
            for year in years:
                # The source's own all-provinces figures for this slice.
                national = dict(
                    _rows(session, sheet, {"Type1": measure_type, "Fiscal year": year})
                )
                per_province: dict[str, dict[str, Decimal]] = {}
                for province, geo_code in PROVINCE_CODES.items():
                    got = _rows(
                        session,
                        sheet,
                        {
                            "Type1": measure_type,
                            "Fiscal year": year,
                            "Province Name": province,
                        },
                    )
                    per_province[geo_code] = dict(got)

                if not national and not any(per_province.values()):
                    continue  # this slice genuinely has no data

                # GATE: per category, the seven provinces must sum to the
                # source's own all-provinces figure.
                for category, national_value in national.items():
                    summed = sum(
                        (p.get(category, Decimal(0)) for p in per_province.values()),
                        Decimal(0),
                    )
                    if abs(summed - national_value) > SUM_TOLERANCE:
                        problems.append(
                            f"{code} {year} {category!r}: provinces sum to {summed:,} "
                            f"but the source publishes {national_value:,} "
                            f"(diff {summed - national_value:,})"
                        )

                period = dashboard_year_to_period_label(year)
                for geo_code, cats in per_province.items():
                    for category, value in cats.items():
                        rows.append(ProvRow(code, geo_code, period, category, value))
                    if cats:
                        rows.append(
                            ProvRow(
                                code, geo_code, period, "",
                                sum(cats.values(), Decimal(0)),
                            )
                        )
            print(f"  {code:34s} {len([r for r in rows if r.indicator_code == code]):5d} rows")
    return rows, problems


def load(rows: list[ProvRow], dry_run: bool) -> None:
    load_dotenv()
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        raise FiscalLoadError("DATABASE_URL is not set")

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM sources WHERE name_en = %s", (SOURCE_NAME,))
        source_id = _scalar(cur)
        cur.execute(
            "SELECT id FROM datasets WHERE source_id = %s AND name_en = %s",
            (source_id, DATASET_NAME),
        )
        dataset_id = _scalar(cur)
        if dataset_id is None:
            raise FiscalLoadError(f"dataset {DATASET_NAME!r} is not seeded")

        print(f"\nIndicators seeded/updated: {seed_indicators(cur, source_id)}")

        wanted = sorted({r.indicator_code for r in rows})
        cur.execute("SELECT code, id FROM indicators WHERE code = ANY(%s)", (wanted,))
        indicator_ids = {c: i for c, i in cur.fetchall()}
        missing_codes = [c for c in wanted if c not in indicator_ids]
        if missing_codes:
            raise FiscalLoadError(
                f"indicators not seeded: {missing_codes}. Add them to {SEED_CSV}."
            )

        cur.execute("SELECT code, id FROM geographies WHERE level = 'province'")
        geo_ids = {c: i for c, i in cur.fetchall()}
        cur.execute("SELECT id FROM units WHERE code = 'NPR_MILLION'")
        unit_id = _scalar(cur)
        cur.execute(
            "SELECT gregorian_label, id FROM time_periods WHERE period_type = 'fiscal_year'"
        )
        period_ids = {label: pid for label, pid in cur.fetchall()}

        # Existing latest values, keyed the same way, so a re-run loads nothing.
        cur.execute(
            "SELECT o.indicator_id, o.geography_id, o.time_period_id,"
            " o.breakdowns::text, o.value"
            " FROM observations o WHERE o.dataset_id = %s AND o.is_latest",
            (dataset_id,),
        )
        latest: dict[tuple[int, int, int, str], Decimal] = {}
        for iid, gid, pid, bd, val in cur.fetchall():
            latest[(iid, gid, pid, _bkey(json.loads(bd) if bd else {}))] = val

        to_insert: list[tuple[Any, ...]] = []
        unchanged = 0
        for r in rows:
            iid = indicator_ids[r.indicator_code]
            gid = geo_ids[r.geo_code]
            pid = period_ids[r.period_label]
            breakdowns = {"category": r.category} if r.category else {}
            key = (iid, gid, pid, _bkey(breakdowns))
            if latest.get(key) == r.value:
                unchanged += 1
                continue
            to_insert.append(
                (iid, gid, pid, dataset_id, r.value, unit_id, json.dumps(breakdowns))
            )

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
            "  release_id, value, unit_id, breakdowns, status)"
            " VALUES (%s, %s, %s, %s, " + str(release_id) + ", %s, %s, %s, 'final')",
            to_insert,
        )
        conn.commit()
        print(f"Loaded {len(to_insert)} observations under release {release_id}.")


def _bkey(breakdowns: dict[str, str]) -> str:
    """Stable key for comparing breakdowns across Python and jsonb."""
    return json.dumps(breakdowns, sort_keys=True, separators=(",", ":"))


def main() -> None:
    configure_stdout_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--years", type=int, default=None)
    args = parser.parse_args()

    years = [f"FY{y}" for y in range(FIRST_DASHBOARD_YEAR, LAST_DASHBOARD_YEAR + 1)]
    if args.years:
        years = years[-args.years :]

    print(f"Harvesting {len(SHEETS)} provincial sheet(s) x {len(TYPES)} types x "
          f"7 provinces x {len(years)} years — be patient, one call per second:")
    rows, problems = harvest(years)
    print(f"\nHarvested {len(rows):,} observations.")

    if problems:
        print(f"\nCROSS-CHECK FAILED ({len(problems)}) — nothing will be loaded:")
        for p in problems[:15]:
            print(f"  {p}")
        raise FiscalLoadError(
            f"{len(problems)} slice(s) where the seven provinces do not sum to the "
            "source's own all-provinces figure. A province or category is missing."
        )
    print("Cross-check: the seven provinces sum to the published national figure "
          "for every category, year and type.")

    load(rows, args.dry_run)


if __name__ == "__main__":
    main()
