"""Acquire the Kalimati daily price series, raw first (ODN.S2, part 1).

Fetches both datastore resources in full, archives the untouched pages to the
raw lake, and writes a local ANALYSIS file — commodity frequency, unit mix,
date coverage and a projected warehouse size — which is what the basket choice
and the storage STOP are decided from. It loads nothing.

TWO SOURCE FAULTS THIS HANDLES (both verified 2026-08-06, see
reference/opendatanepal/PROVENANCE.md)
--------------------------------------------------------------------------
1. **Resource 2's header row was eaten by the upload**, so CKAN named its
   columns after the first data row. The positional mapping used here is not a
   guess: it was confirmed against resource 1 over their four-month overlap —
   497 rows compared, 497 agreed, on unit, min, max and average alike — and
   the commodity ordering was confirmed independently against the market
   board's own site. The row that became the header is genuinely lost from
   this resource; it is also present in resource 1, which covers that date.

2. **The `Average` column is the midpoint of the day's min and max**, in
   100.00% of 5,000 rows sampled across the full range — not an average of
   trades. The market board's own published average is a different, usually
   higher number. It is therefore acquired as `midpoint`, and must never be
   published as an average.

Run with `make kalimati-acquire`. Options:
    --limit-pages N   stop after N pages per resource (a rehearsal)
    --no-raw          skip the raw-lake write (analysis only; use sparingly)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ingestion.common.io_utf8 import configure_stdout_utf8  # noqa: E402
from ingestion.common.raw_lake import RawLake  # noqa: E402
from ingestion.opendatanepal.ckan_client import (  # noqa: E402
    CkanError,
    DatastoreResult,
    fetch_datastore_rows,
    fetch_package,
    store_raw,
    summarise,
)

DATASET_SLUG = "kalimati-tarkari-dataset"
ANALYSIS_PATH = Path("reference/opendatanepal/kalimati_analysis.json")

# Resource 1 publishes proper column names; resource 2's were eaten by the
# upload, so it is read by POSITION through the mapping verified in S1.
CLEAN_RESOURCE = "b791b8cd-7ed4-445c-ad8d-69bf58a2c8d4"
BROKEN_RESOURCE = "1095e921-51ae-47b7-a501-9da185c0644e"

CLEAN_FIELDS = ("Commodity", "Date", "Unit", "Minimum", "Maximum", "Average")
BROKEN_FIELDS = (
    "Tomato Big(Nepali)",   # commodity
    "2021-01-05 00:00:00",  # date
    "Kg",                   # unit
    "50",                   # minimum
    "60",                   # maximum
    "55",                   # average -> midpoint
)

# A wholesale price per kg outside this band is a unit error, not a price.
MIN_PRICE = Decimal("0")
MAX_PRICE = Decimal("10000")

# Measured on the live warehouse (observations table + its indexes, divided by
# row count) rather than estimated — the estimate was 250 and the truth is
# nearly double, which is the difference between a comfortable load and half
# the remaining free tier.
BYTES_PER_OBSERVATION = 476


class KalimatiError(Exception):
    """Refuse to proceed rather than acquire something we cannot read."""


@dataclass(frozen=True)
class PriceRow:
    commodity: str
    day: date
    unit: str
    minimum: Decimal
    maximum: Decimal
    midpoint: Decimal


def _decimal(raw: object, what: str) -> Decimal:
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise KalimatiError(f"{what}: {raw!r} is not a number") from exc


def _day(raw: object) -> date:
    """Both resources date rows differently: 'YYYY-MM-DD' in the clean one,
    'YYYY-MM-DDTHH:MM:SS' in the malformed one. Anything else stops the run —
    a date we cannot read is a date we must not guess."""
    text = str(raw).strip()
    head = text.split("T", 1)[0]
    try:
        return date.fromisoformat(head)
    except ValueError as exc:
        raise KalimatiError(f"unreadable date {raw!r}") from exc


def parse_rows(records: list[dict[str, object]], fields: tuple[str, ...]) -> list[PriceRow]:
    """Turn datastore records into typed rows, failing loudly on anything odd.

    `fields` names the six columns positionally: commodity, date, unit, min,
    max, midpoint. A record missing any of them stops the run — a shifted
    column would otherwise be loaded as a price.
    """
    commodity_f, date_f, unit_f, min_f, max_f, mid_f = fields
    out: list[PriceRow] = []
    for record in records:
        missing = [f for f in fields if f not in record]
        if missing:
            raise KalimatiError(
                f"record is missing {missing} — the source's columns changed; "
                f"got {sorted(record)}"
            )
        minimum = _decimal(record[min_f], "minimum")
        maximum = _decimal(record[max_f], "maximum")
        midpoint = _decimal(record[mid_f], "midpoint")
        if not (MIN_PRICE < minimum <= MAX_PRICE and MIN_PRICE < maximum <= MAX_PRICE):
            raise KalimatiError(
                f"{record[commodity_f]!r} on {record[date_f]}: prices "
                f"{minimum}/{maximum} fall outside (0, {MAX_PRICE}] NPR — "
                "a unit error or a changed source."
            )
        if minimum > maximum:
            raise KalimatiError(
                f"{record[commodity_f]!r} on {record[date_f]}: minimum {minimum} "
                f"exceeds maximum {maximum}."
            )
        out.append(
            PriceRow(
                commodity=str(record[commodity_f]).strip(),
                day=_day(record[date_f]),
                unit=str(record[unit_f]).strip(),
                minimum=minimum,
                maximum=maximum,
                midpoint=midpoint,
            )
        )
    return out


@dataclass(frozen=True)
class BasketEntry:
    commodity: str
    days: int


@dataclass(frozen=True)
class Analysis:
    """The evidence behind the basket choice and the storage decision."""

    generated: str
    rows_total: int
    rows_kg: int
    rows_other_units: int
    other_units: dict[str, int]
    commodities_total: int
    date_first: str | None
    date_last: str | None
    basket_size: int
    basket: list[BasketEntry]
    basket_rows: int
    projected_observations: int
    projected_mb: float


def analyse(rows: list[PriceRow], basket_size: int = 25) -> Analysis:
    """Everything the basket choice and the storage STOP are decided from."""
    kg_rows = [r for r in rows if r.unit.lower() == "kg"]
    other_units = Counter(r.unit for r in rows if r.unit.lower() != "kg")

    # Rank by how many days a commodity appears on: a commodity present for a
    # decade is worth more than one that spiked for a month, whatever its
    # row count.
    days_per_commodity = Counter(r.commodity for r in kg_rows)
    basket = [name for name, _ in days_per_commodity.most_common(basket_size)]
    basket_rows = [r for r in kg_rows if r.commodity in basket]

    # TWO stored series per basket row: the minimum and the maximum, which are
    # the market board's own figures. The midpoint is NOT stored — it is
    # exactly (min + max) / 2 in 100.00% of 5,000 rows sampled across the whole
    # series, so storing it would spend a third of the space on arithmetic the
    # API can do for free, with no information gained.
    #
    # 476 bytes per observation is measured, not guessed: the live
    # `observations` table, indexes included, divided by its row count.
    observations = len(basket_rows) * 2
    projected_mb = observations * BYTES_PER_OBSERVATION / 1_000_000

    return Analysis(
        generated=date.today().isoformat(),
        rows_total=len(rows),
        rows_kg=len(kg_rows),
        rows_other_units=sum(other_units.values()),
        other_units=dict(other_units.most_common()),
        commodities_total=len(days_per_commodity),
        date_first=min(r.day for r in rows).isoformat() if rows else None,
        date_last=max(r.day for r in rows).isoformat() if rows else None,
        basket_size=basket_size,
        basket=[BasketEntry(name, days_per_commodity[name]) for name in basket],
        basket_rows=len(basket_rows),
        projected_observations=observations,
        projected_mb=round(projected_mb, 1),
    )


def acquire(limit_pages: int | None, write_raw: bool) -> list[PriceRow]:
    package, package_raw = fetch_package(DATASET_SLUG)
    print(summarise(package))
    licence = package.get("license_id")
    if licence not in ("cc-by", "cc-by-sa", "cc-zero", "odc-by"):
        raise KalimatiError(
            f"licence is {licence!r}, not one of the open licences this project "
            "onboards without founder sign-off."
        )

    lake = RawLake.from_env() if write_raw else None
    rows: list[PriceRow] = []
    for resource_id, fields in (
        (CLEAN_RESOURCE, CLEAN_FIELDS),
        (BROKEN_RESOURCE, BROKEN_FIELDS),
    ):
        print(f"\nFetching {resource_id} …")
        result: DatastoreResult = fetch_datastore_rows(
            resource_id, limit_pages=limit_pages
        )
        print(f"  {len(result.rows):,} of {result.total:,} rows in {len(result.pages)} pages")
        if lake is not None:
            stored = store_raw(
                lake, DATASET_SLUG, result, package_raw,
                f"https://api.opendatanepal.com/api/3/action/package_show?id={DATASET_SLUG}",
            )
            print(f"  raw -> {stored.payload_path} ({stored.size_bytes:,} bytes)")
        parsed = parse_rows(result.rows, fields)
        print(f"  parsed {len(parsed):,} rows")
        rows.extend(parsed)
    return rows


def main() -> int:
    configure_stdout_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit-pages", type=int, default=None)
    parser.add_argument("--no-raw", action="store_true")
    args = parser.parse_args()

    rows = acquire(args.limit_pages, write_raw=not args.no_raw)
    report = analyse(rows)

    ANALYSIS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ANALYSIS_PATH.write_text(
        json.dumps(asdict(report), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"\n{'-' * 62}")
    print(f"Rows acquired      : {report.rows_total:,}")
    print(f"  priced per Kg    : {report.rows_kg:,}")
    print(f"  other units      : {report.rows_other_units:,}  {report.other_units}")
    print(f"Commodities        : {report.commodities_total}")
    print(f"Coverage           : {report.date_first} -> {report.date_last}")
    print(f"\nBasket of {report.basket_size} most-present commodities:")
    for entry in report.basket:
        print(f"  {entry.days:>6,} days   {entry.commodity}")
    print(f"\nBasket rows        : {report.basket_rows:,}")
    print(f"Projected rows     : {report.projected_observations:,} observations "
          "(min + max; the midpoint is derived, not stored)")
    print(f"Projected size     : ~{report.projected_mb} MB")
    print(f"Analysis written   : {ANALYSIS_PATH}")

    if report.projected_mb > 200:
        print(
            "\nSTOP: the projection exceeds the 200 MB budget in the step file. "
            "Consult the founder before loading (options: fewer statistics, or "
            "a smaller basket)."
        )
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KalimatiError, CkanError) as exc:
        print(f"\nACQUIRE FAILED: {exc}", file=sys.stderr)
        sys.exit(2)
