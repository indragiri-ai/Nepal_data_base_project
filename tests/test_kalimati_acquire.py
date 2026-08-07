"""ODN.S2 acquisition tests. Offline: no network, no database.

The parser reads two resources whose columns are named differently — one
properly, one because its header row was eaten on upload — through the same
positional contract. These pin that contract, and the refusals around it.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from ingestion.opendatanepal.kalimati_acquire import (
    BROKEN_FIELDS,
    CLEAN_FIELDS,
    KalimatiError,
    analyse,
    parse_rows,
)


def _clean_record(**over: object) -> dict[str, object]:
    record: dict[str, object] = {
        "Commodity": "Tomato Big(Nepali)",
        "Date": "2013-06-16",
        "Unit": "Kg",
        "Minimum": "35.0",
        "Maximum": "40.0",
        "Average": "37.5",
    }
    record.update(over)
    return record


def _broken_record(**over: object) -> dict[str, object]:
    record: dict[str, object] = {
        "Tomato Big(Nepali)": "Tomato Big(Indian)",
        "2021-01-05 00:00:00": "2021-01-05T00:00:00",
        "Kg": "Kg",
        "50": 50,
        "60": 60,
        "55": 55,
    }
    record.update(over)
    return record


# --- the two column contracts ------------------------------------------------


def test_the_clean_resource_parses_the_recorded_sample_row() -> None:
    (row,) = parse_rows([_clean_record()], CLEAN_FIELDS)
    assert row.commodity == "Tomato Big(Nepali)"
    assert row.day == date(2013, 6, 16)
    assert row.unit == "Kg"
    assert row.minimum == Decimal("35.0")
    assert row.maximum == Decimal("40.0")
    assert row.midpoint == Decimal("37.5")


def test_the_malformed_resource_parses_through_the_verified_positions() -> None:
    """Its column names are its own first data row; positions carry the meaning.

    The mapping is not assumed — it was confirmed over the two resources'
    four-month overlap (497 rows, 497 agreeing) and against the market board's
    own site. This test pins it so a future edit cannot quietly shift a column.
    """
    (row,) = parse_rows([_broken_record()], BROKEN_FIELDS)
    assert row.commodity == "Tomato Big(Indian)"
    assert row.day == date(2021, 1, 5)  # the 'T00:00:00' suffix is handled
    assert row.minimum == Decimal("50")
    assert row.maximum == Decimal("60")
    assert row.midpoint == Decimal("55")


def test_a_missing_column_stops_the_run() -> None:
    # A shifted or renamed column would otherwise be loaded as a price.
    record = _clean_record()
    del record["Maximum"]
    with pytest.raises(KalimatiError, match="missing"):
        parse_rows([record], CLEAN_FIELDS)


def test_an_unreadable_date_stops_the_run() -> None:
    with pytest.raises(KalimatiError, match="unreadable date"):
        parse_rows([_clean_record(Date="16/06/2013")], CLEAN_FIELDS)


def test_a_non_numeric_price_stops_the_run() -> None:
    with pytest.raises(KalimatiError, match="not a number"):
        parse_rows([_clean_record(Minimum="n/a")], CLEAN_FIELDS)


# --- the quality band --------------------------------------------------------


@pytest.mark.parametrize("price", ["0", "-5", "10001"])
def test_a_price_outside_the_band_stops_the_run(price: str) -> None:
    # Generous on purpose: it is there to catch a unit error (the 1000x
    # classic), not to second-guess the market.
    with pytest.raises(KalimatiError, match="outside"):
        parse_rows([_clean_record(Minimum=price, Maximum=price)], CLEAN_FIELDS)


def test_a_minimum_above_the_maximum_stops_the_run() -> None:
    with pytest.raises(KalimatiError, match="exceeds maximum"):
        parse_rows([_clean_record(Minimum="90", Maximum="10")], CLEAN_FIELDS)


def test_a_price_at_the_top_of_the_band_is_allowed() -> None:
    (row,) = parse_rows([_clean_record(Minimum="10000", Maximum="10000")], CLEAN_FIELDS)
    assert row.maximum == Decimal("10000")


# --- the analysis that decides the basket and the storage STOP ---------------


def _rows(n_days: int, commodity: str, unit: str = "Kg") -> list[dict[str, object]]:
    return [
        _clean_record(
            Commodity=commodity,
            Unit=unit,
            Date=date(2020, 1, 1).replace(day=1 + (i % 28)).isoformat(),
        )
        for i in range(n_days)
    ]


def test_non_kg_rows_are_excluded_from_the_basket_but_counted() -> None:
    """Never silently convert a unit.

    'Doz' and '1 Pc' rows are real prices for a different thing; converting
    them to a per-kg figure would need a weight we do not have. They are
    reported instead.
    """
    records = _rows(5, "Tomato") + _rows(3, "Coconut", unit="1 Pc")
    report = analyse(parse_rows(records, CLEAN_FIELDS))
    assert report.rows_total == 8
    assert report.rows_kg == 5
    assert report.rows_other_units == 3
    assert report.other_units == {"1 Pc": 3}
    assert [b.commodity for b in report.basket] == ["Tomato"]


def test_the_basket_is_the_most_present_commodities() -> None:
    # Presence over a decade beats a brief spike, so ranking is by day count.
    records = _rows(10, "Tomato") + _rows(6, "Potato") + _rows(2, "Kiwi")
    report = analyse(parse_rows(records, CLEAN_FIELDS), basket_size=2)
    assert [b.commodity for b in report.basket] == ["Tomato", "Potato"]
    assert report.basket_rows == 16


def test_the_projection_counts_two_series_per_row_not_three() -> None:
    """Only the minimum and maximum are stored; the midpoint is derived.

    The midpoint is exactly (min + max) / 2 in every row of the source, so
    storing it would spend a third of the space on arithmetic and gain nothing.
    """
    report = analyse(parse_rows(_rows(10, "Tomato"), CLEAN_FIELDS), basket_size=1)
    assert report.projected_observations == 20


def test_coverage_dates_come_from_the_data_not_the_titles() -> None:
    # The resource titles are wrong about their own end dates (verified in S1),
    # so coverage is always read off the rows.
    report = analyse(parse_rows(_rows(28, "Tomato"), CLEAN_FIELDS))
    assert report.date_first == "2020-01-01"
    assert report.date_last == "2020-01-28"
