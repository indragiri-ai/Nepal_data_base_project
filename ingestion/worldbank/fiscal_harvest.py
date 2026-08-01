"""Harvest the federal + provincial fiscal grid into a reviewable staging file (WBF.S2).

Scraped data goes through staging and human review before it reaches the
warehouse (house rule 3, and the NRB pattern). This module does the harvest,
the arithmetic checks and nothing else: it WRITES NO DATABASE ROWS. Its output
is a staging CSV plus a summary a human can actually read, which is the founder
approval gate. Promotion is a separate, later step.

Why a grid walk at all: a sheet's CSV contains only what its current view
renders. Federal sheets default to all seven years at the top of the hierarchy;
provincial sheets default to one year aggregated over all provinces. Tableau URL
filters drive the view, so the loader asks for each slice it needs.

Every slice is checked, not trusted:
  * a filter that matches nothing returns an EMPTY CSV, not an error, so an
    expected-but-missing slice is a hard failure;
  * where the source publishes both a parent total and its parts, the parts
    must sum to the parent (the census SumRule idea), else the category list
    is incomplete and the load stops.

Run with `make wb-fiscal-harvest`. Options:
    --limit-sheets N   harvest only the first N sheets (testing)
    --years N          harvest only the most recent N fiscal years (testing)
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ingestion.common.io_utf8 import configure_stdout_utf8  # noqa: E402
from ingestion.worldbank.fiscal_acquire import (  # noqa: E402
    REQUEST_PAUSE_S,
    fetch_sheet,
    open_session,
)
from ingestion.worldbank.fiscal_layout import (  # noqa: E402
    ALL_SHEETS,
    FEDERAL_GEO_CODE,
    FEDERAL_SHEETS,
    FIRST_DASHBOARD_YEAR,
    LAST_DASHBOARD_YEAR,
    PROVINCE_CODES,
    SheetSpec,
    dashboard_year_to_period_label,
    parse_amount,
)

STAGING_PATH = Path("reference/wb-fiscal/staging_observations.csv")
# Tolerance for the parts-sum-to-parent check. The source publishes one decimal
# place, so rounding across up to five parts can legitimately differ in the last
# place; anything larger is a missing category, not rounding.
SUM_TOLERANCE = Decimal("0.5")


class FiscalHarvestError(Exception):
    """A slice was missing or failed its arithmetic check — never load anyway."""


@dataclass(frozen=True)
class Observation:
    indicator_code: str
    geo_code: str
    period_label: str
    measure_type: str  # "Actual" | "Budget"
    category: str  # "" for the parent total
    value: Decimal
    source_sheet: str
    source_year_label: str


def _column(header: list[str], *names: str) -> int:
    for name in names:
        if name in header:
            return header.index(name)
    raise FiscalHarvestError(f"none of {names} in header {header}")


def _rows_for(
    session: requests.Session, spec: SheetSpec, filters: dict[str, str]
) -> tuple[list[str], list[list[str]]]:
    payload = fetch_sheet(session, spec.sheet, filters)
    rows = payload.rows
    if not rows:
        raise FiscalHarvestError(f"{spec.sheet} {filters}: empty response (no header)")
    time.sleep(REQUEST_PAUSE_S)
    return rows[0], rows[1:]


def harvest_federal(
    session: requests.Session, spec: SheetSpec, years: list[str]
) -> list[Observation]:
    """Federal sheets render all seven years at once, so one call per slice."""
    out: list[Observation] = []
    for measure_type in spec.types:
        # The parent total: no Group2 filter.
        header, body = _rows_for(session, spec, {"Type1": measure_type})
        if not body:
            raise FiscalHarvestError(
                f"{spec.sheet} Type1={measure_type}: no rows. The sheet or its "
                "Type1 values changed — re-run the S1 spike."
            )
        year_ix = _column(header, "Year1", "Fiscal year", "FY1")
        val_ix = 1  # the measure always sits in column 1
        for row in body:
            label = row[year_ix]
            if label not in years:
                continue
            out.append(
                Observation(
                    indicator_code=spec.indicator_code,
                    geo_code=FEDERAL_GEO_CODE,
                    period_label=dashboard_year_to_period_label(label),
                    measure_type=measure_type,
                    category="",
                    value=parse_amount(row[val_ix]),
                    source_sheet=spec.sheet,
                    source_year_label=label,
                )
            )

        for category in spec.categories:
            header, body = _rows_for(
                session, spec, {"Type1": measure_type, "Group2": category}
            )
            if not body:
                raise FiscalHarvestError(
                    f"{spec.sheet} Type1={measure_type} Group2={category!r}: no rows. "
                    "A filter that matches nothing returns empty, not an error — "
                    "the category list in fiscal_layout is stale."
                )
            year_ix = _column(header, "Year1", "Fiscal year", "FY1")
            for row in body:
                label = row[year_ix]
                if label not in years:
                    continue
                out.append(
                    Observation(
                        indicator_code=spec.indicator_code,
                        geo_code=FEDERAL_GEO_CODE,
                        period_label=dashboard_year_to_period_label(label),
                        measure_type=measure_type,
                        category=category,
                        value=parse_amount(row[val_ix]),
                        source_sheet=spec.sheet,
                        source_year_label=label,
                    )
                )
    return out


def harvest_provincial(
    session: requests.Session, spec: SheetSpec, years: list[str]
) -> list[Observation]:
    """Provincial sheets render one year at a time, listing the categories, so
    one call per province-year returns that province's whole breakdown."""
    out: list[Observation] = []
    for measure_type in spec.types:
        for province, geo_code in PROVINCE_CODES.items():
            for year in years:
                filters = {
                    "Type1": measure_type,
                    "Province Name": province,
                    "Fiscal year": year,
                }
                header, body = _rows_for(session, spec, filters)
                if not body:
                    # Legitimately possible (a province may have no Budget row
                    # in an early year); recorded as absent rather than zero.
                    continue
                cat_ix = _column(header, "Group2", "Group2 (Prov!Grant)")
                for row in body:
                    out.append(
                        Observation(
                            indicator_code=spec.indicator_code,
                            geo_code=geo_code,
                            period_label=dashboard_year_to_period_label(year),
                            measure_type=measure_type,
                            category=row[cat_ix] if spec.categories else "",
                            value=parse_amount(row[1]),
                            source_sheet=spec.sheet,
                            source_year_label=year,
                        )
                    )
    return out


def check_sums(observations: list[Observation]) -> list[str]:
    """Parts must sum to their parent. Returns human-readable failures."""
    parents: dict[tuple[str, str, str, str], Decimal] = {}
    parts: dict[tuple[str, str, str, str], Decimal] = {}
    for obs in observations:
        key = (obs.indicator_code, obs.geo_code, obs.period_label, obs.measure_type)
        if obs.category:
            parts[key] = parts.get(key, Decimal(0)) + obs.value
        else:
            parents[key] = obs.value

    problems: list[str] = []
    for key, total in sorted(parents.items()):
        if key not in parts:
            continue  # a sheet with no published breakdown
        diff = parts[key] - total
        if abs(diff) > SUM_TOLERANCE:
            code, geo, period, mtype = key
            problems.append(
                f"{code} {geo} {period} {mtype}: parts {parts[key]:,} vs "
                f"parent {total:,} (diff {diff:,})"
            )
    return problems


def write_staging(observations: list[Observation], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "indicator_code", "geo_code", "period_label", "measure_type",
            "category", "value_npr_million", "source_sheet", "source_year_label",
        ])
        for o in sorted(
            observations,
            key=lambda x: (x.indicator_code, x.geo_code, x.period_label,
                           x.measure_type, x.category),
        ):
            writer.writerow([
                o.indicator_code, o.geo_code, o.period_label, o.measure_type,
                o.category, o.value, o.source_sheet, o.source_year_label,
            ])


def main() -> None:
    configure_stdout_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit-sheets", type=int, default=None)
    parser.add_argument("--years", type=int, default=None)
    args = parser.parse_args()

    years = [
        f"FY{y}" for y in range(FIRST_DASHBOARD_YEAR, LAST_DASHBOARD_YEAR + 1)
    ]
    if args.years:
        years = years[-args.years :]

    sheets = list(ALL_SHEETS)
    if args.limit_sheets:
        sheets = sheets[: args.limit_sheets]

    session = open_session()
    time.sleep(REQUEST_PAUSE_S)

    observations: list[Observation] = []
    for spec in sheets:
        harvest = harvest_federal if spec in FEDERAL_SHEETS else harvest_provincial
        got = harvest(session, spec, years)
        observations.extend(got)
        print(f"  {spec.sheet:32s} {len(got):5d} observations")

    print(f"\nHarvested {len(observations):,} observations across {len(sheets)} sheet(s).")

    problems = check_sums(observations)
    if problems:
        print(f"\nSUM CHECK FAILED ({len(problems)} slice(s)) — nothing will be promoted:")
        for p in problems[:20]:
            print(f"  {p}")
        raise FiscalHarvestError(
            f"{len(problems)} slice(s) whose parts do not sum to their parent. "
            "A category is missing from fiscal_layout, or the source changed."
        )
    print("Sum checks: every published breakdown sums to its parent.")

    write_staging(observations, STAGING_PATH)
    print(f"\nStaged to {STAGING_PATH} — NOTHING has been written to the warehouse.")
    print("Review the file, then promotion is a separate step (WBF.S2 gate).")


if __name__ == "__main__":
    main()
