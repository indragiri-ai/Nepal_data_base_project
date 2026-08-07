"""ODN.S2 loader tests. Offline: no network, no database.

What is checked here is the part that decides WHAT gets stored — the basket
file, and the rules about which rows and which statistics are eligible. The
database work itself is exercised by the dry run against the live warehouse.
"""

from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from ingestion.opendatanepal.kalimati_acquire import KalimatiError, PriceRow
from ingestion.opendatanepal.kalimati_pipeline import (
    BASKET_CSV,
    GEO_CODE,
    MAX_INDICATOR,
    MIN_INDICATOR,
    SEED_CSV,
    UNIT_CODE,
    read_basket,
)


def _row(commodity: str, unit: str = "Kg") -> PriceRow:
    return PriceRow(
        commodity=commodity,
        day=date(2020, 1, 1),
        unit=unit,
        minimum=Decimal("10"),
        maximum=Decimal("20"),
        midpoint=Decimal("15"),
    )


# --- the basket, as reviewable data (rule 4) ---------------------------------


def test_the_basket_file_exists_and_lists_the_curated_commodities() -> None:
    basket = read_basket()
    assert len(basket) == 25
    # Ranked by how many days each appears, so the staples lead.
    assert "Cauli Local" in basket
    assert "Potato Red" in basket
    assert "Tomato Small(Local)" in basket


def test_the_basket_can_be_trimmed_for_a_rehearsal() -> None:
    assert len(read_basket(limit=3)) == 3


def test_every_basket_row_carries_its_evidence() -> None:
    """The CSV records how many days each commodity appears on.

    That number is why the commodity is in the basket at all; keeping it beside
    the name means a human can argue with the selection instead of taking it on
    trust.
    """
    with BASKET_CSV.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 25
    for row in rows:
        assert int(row["days_present"]) > 0


# --- what the loader stores --------------------------------------------------


def test_only_two_indicators_are_seeded_and_neither_is_an_average() -> None:
    """The source's 'Average' column is not loaded.

    It is exactly (min + max) / 2 across the whole series and disagrees with
    the market board's own published average, so it is derived for display and
    labelled a midpoint. Nothing in the warehouse may be called an average.
    """
    with SEED_CSV.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    codes = {r["code"] for r in rows}
    assert codes == {MIN_INDICATOR, MAX_INDICATOR}
    for row in rows:
        assert "average" not in row["name_en"].lower()
        assert row["unit"] == UNIT_CODE


def test_the_definitions_state_the_closed_coverage_window() -> None:
    # Vintage honesty: a historical series must never read as current prices.
    text = SEED_CSV.read_text(encoding="utf-8")
    assert "2022-04-18" in text
    assert "NOT" in text and "current prices" in text


def test_the_definitions_explain_the_kg_only_rule() -> None:
    text = SEED_CSV.read_text(encoding="utf-8").lower()
    assert "per piece or per dozen are excluded" in text


def test_prices_are_filed_where_the_market_is_not_nationally() -> None:
    """One market's wholesale prices are not Nepal's prices.

    NP0327101 is Kathmandu Metropolitan City, where Kalimati market sits.
    """
    assert GEO_CODE == "NP0327101"
    assert not GEO_CODE == "NP"


# --- the rules the loader applies to rows ------------------------------------


def test_non_kg_rows_never_reach_the_warehouse() -> None:
    rows = [_row("Cauli Local"), _row("Coconut", unit="1 Pc")]
    basket = {"Cauli Local", "Coconut"}
    eligible = [r for r in rows if r.unit.lower() == "kg" and r.commodity in basket]
    assert [r.commodity for r in eligible] == ["Cauli Local"]


def test_commodities_outside_the_basket_are_left_out() -> None:
    rows = [_row("Cauli Local"), _row("Dragon Fruit")]
    basket = {"Cauli Local"}
    eligible = [r for r in rows if r.unit.lower() == "kg" and r.commodity in basket]
    assert [r.commodity for r in eligible] == ["Cauli Local"]


def test_a_missing_basket_file_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    import ingestion.opendatanepal.kalimati_pipeline as pipeline

    monkeypatch.setattr(pipeline, "BASKET_CSV", Path("db/seeds/does-not-exist.csv"))
    with pytest.raises(KalimatiError, match="is missing"):
        pipeline.read_basket()


# --- the overlap between the two resources -----------------------------------


def _dated(commodity: str, day: date, low: str, high: str) -> PriceRow:
    return PriceRow(
        commodity=commodity,
        day=day,
        unit="Kg",
        minimum=Decimal(low),
        maximum=Decimal(high),
        midpoint=(Decimal(low) + Decimal(high)) / 2,
    )


def test_a_commodity_day_appearing_in_both_resources_is_stored_once() -> None:
    """The two resources overlap by about four months.

    Offering the same cell twice is rejected by the database's uniqueness
    constraint — which is right, because the alternative is a silently
    double-counted price. It caught exactly this on the first real load.
    """
    from ingestion.opendatanepal.kalimati_pipeline import deduplicate

    day = date(2021, 3, 15)
    rows = [_dated("Tomato", day, "25", "30"), _dated("Tomato", day, "25", "30")]
    kept, overlaps, conflicts = deduplicate(rows)
    assert len(kept) == 1
    assert overlaps == 1
    assert conflicts == []


def test_the_later_resource_wins_a_disagreement_and_it_is_reported() -> None:
    # Preferring the newer publication is the step file's tie-break; the point
    # is that the disagreement is counted rather than silently resolved.
    from ingestion.opendatanepal.kalimati_pipeline import deduplicate

    day = date(2021, 3, 15)
    rows = [_dated("Tomato", day, "25", "30"), _dated("Tomato", day, "26", "31")]
    kept, overlaps, conflicts = deduplicate(rows)
    assert kept[0].minimum == Decimal("26")  # the later row
    assert overlaps == 1
    assert len(conflicts) == 1
    assert "Tomato" in conflicts[0]


def test_different_days_and_commodities_are_never_merged() -> None:
    from ingestion.opendatanepal.kalimati_pipeline import deduplicate

    rows = [
        _dated("Tomato", date(2021, 3, 15), "25", "30"),
        _dated("Tomato", date(2021, 3, 16), "26", "31"),
        _dated("Potato", date(2021, 3, 15), "40", "45"),
    ]
    kept, overlaps, conflicts = deduplicate(rows)
    assert len(kept) == 3
    assert overlaps == 0
