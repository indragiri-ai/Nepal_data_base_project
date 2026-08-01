"""WBF.S2 layout-registry tests. Pure logic, no network, no database."""

from __future__ import annotations

from decimal import Decimal

import pytest

from ingestion.worldbank.fiscal_layout import (
    ALL_SHEETS,
    FEDERAL_SHEETS,
    PROVINCE_CODES,
    PROVINCIAL_SHEETS,
    SOURCE_UNIT_LABEL,
    SUM_CHECKS,
    dashboard_year_to_period_label,
    parse_amount,
)


def test_recorded_sum_checks_still_hold() -> None:
    """The evidence that the category lists are COMPLETE.

    These are the two exact sums measured from the dashboard. They are the
    reason the registry claims its category lists are exhaustive, so they are
    asserted rather than left as prose.
    """
    for label, parts, total in SUM_CHECKS:
        assert sum(parts) == total, label


def test_all_seven_provinces_map_to_distinct_p_codes() -> None:
    assert len(PROVINCE_CODES) == 7
    assert sorted(PROVINCE_CODES.values()) == [f"NP0{i}" for i in range(1, 8)]


def test_province_spellings_are_the_sources_own() -> None:
    # Load-bearing: the dashboard returns ZERO ROWS AND NO ERROR for a
    # near-miss spelling, so these strings must not be "tidied".
    assert "Sudurpaschim" in PROVINCE_CODES
    assert "Sudurpashchim" not in PROVINCE_CODES  # returns nothing at source
    assert "Madhesh" in PROVINCE_CODES
    assert "Madhes" not in PROVINCE_CODES


def test_dashboard_year_maps_to_the_fiscal_year_it_ends_in() -> None:
    # The dashboard labels by the ENDING Gregorian year: FY2018 = FY 2017/18.
    assert dashboard_year_to_period_label("FY2018") == "FY 2017/18"
    assert dashboard_year_to_period_label("FY2024") == "FY 2023/24"
    assert dashboard_year_to_period_label("FY 2024") == "FY 2023/24"


def test_dashboard_year_rejects_years_the_source_never_published() -> None:
    # Inventing a period for an unpublished label is exactly rule 1's failure.
    for bad in ("FY2017", "FY2025", "2018", "FYxxxx", ""):
        with pytest.raises(ValueError):
            dashboard_year_to_period_label(bad)


def test_debt_stock_carries_actuals_only() -> None:
    # Measured: Type1=Budget returns zero rows for this sheet. Assuming both
    # types exist everywhere would silently fabricate an empty budget series.
    debt = next(s for s in FEDERAL_SHEETS if s.indicator_code == "FISCAL_DEBT_STOCK")
    assert debt.types == ("Actual",)


def test_every_sheet_declares_at_least_one_type_and_a_unique_code() -> None:
    codes = [s.indicator_code for s in ALL_SHEETS]
    assert len(codes) == len(set(codes)), "indicator codes must be unique"
    for spec in ALL_SHEETS:
        assert spec.types, f"{spec.sheet} declares no Type1 values"
        assert spec.tier in ("federal", "provincial")
        assert spec.topic == "economy"


def test_federal_and_provincial_revenue_share_the_same_categories() -> None:
    # Both tiers use the same fiscal classification; if they ever diverge the
    # registry must say so explicitly rather than quietly reuse one list.
    fed = next(s for s in FEDERAL_SHEETS if s.sheet == "Federal Revenue")
    prov = next(s for s in PROVINCIAL_SHEETS if s.sheet == "Provincial Revenue")
    assert set(fed.categories) == set(prov.categories)


def test_parse_amount_handles_the_sources_formatting() -> None:
    assert parse_amount('"1,013,490.1"'.strip('"')) == Decimal("1013490.1")
    assert parse_amount("766,036.1") == Decimal("766036.1")
    assert parse_amount("-116,586.07") == Decimal("-116586.07")
    assert parse_amount("0") == Decimal("0")


def test_parse_amount_refuses_to_turn_a_gap_into_a_zero() -> None:
    # `*` means "not drilled into", not "zero". Returning 0 would publish a
    # number the source never stated.
    for blank in ("*", "", "   ", "-", "null"):
        with pytest.raises(ValueError):
            parse_amount(blank)


def test_the_unit_is_the_string_the_source_publishes() -> None:
    assert SOURCE_UNIT_LABEL == "NPR Million"
