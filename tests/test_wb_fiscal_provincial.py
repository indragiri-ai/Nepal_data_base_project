"""WBF.S2 provincial-loader tests. Offline: no network, no database."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from ingestion.worldbank.fiscal_layout import PROVINCE_CODES
from ingestion.worldbank.fiscal_pipeline import FiscalLoadError
from ingestion.worldbank.fiscal_provincial import (
    SHEETS,
    SUM_TOLERANCE,
    TYPES,
    ProvRow,
    _bkey,
    _category_column,
)


def test_category_column_handles_both_header_shapes() -> None:
    # The Grants sheet names its columns differently from Revenue/Expenditure.
    plain = ["Group2", "measure_%TOT_G3", "Fiscal year", "Group0"]
    grants = ["Group2 (Prov!Grant)", "grant_%TOT_G3", "Fiscal year (prov!grant)"]
    assert _category_column(plain) == 0
    assert _category_column(grants) == 0


def test_category_column_fails_loudly_on_an_unknown_header() -> None:
    # A renamed column must stop the load, not silently index the wrong field.
    with pytest.raises(FiscalLoadError, match="no category column"):
        _category_column(["Year1", "value", "Something else"])


def test_breakdown_key_is_stable_across_orderings() -> None:
    # The idempotency check compares Python dicts against Postgres jsonb, which
    # reorders keys; the key must not depend on insertion order.
    assert _bkey({"category": "Taxes"}) == _bkey({"category": "Taxes"})
    assert _bkey({}) == "{}"
    assert json.loads(_bkey({"category": "Grants"})) == {"category": "Grants"}


def test_a_headline_row_carries_no_category() -> None:
    # breakdowns = {} is what /v1/data/geo filters on for the choropleth.
    total = ProvRow("FISCAL_PROV_REVENUE_ACTUAL", "NP03", "FY 2023/24", "", Decimal("1"))
    part = ProvRow("FISCAL_PROV_REVENUE_ACTUAL", "NP03", "FY 2023/24", "Taxes", Decimal("1"))
    assert total.category == ""
    assert part.category == "Taxes"


def test_the_cross_check_would_catch_a_missing_province() -> None:
    """The gate that makes a derived provincial total safe to publish.

    Reproduces the spike's real figures: the seven provinces' FY2024 tax
    revenue sums to the published all-provinces total exactly. Drop one
    province and the gate must fire.
    """
    per_province = [
        Decimal("12320.47"), Decimal("11275.08"), Decimal("20704.84"),
        Decimal("12907.97"), Decimal("11828.10"), Decimal("7766.79"),
        Decimal("8166.11"),
    ]
    published_national = Decimal("84969.36")

    assert abs(sum(per_province) - published_national) <= SUM_TOLERANCE

    missing_one = sum(per_province[:-1])
    assert abs(missing_one - published_national) > SUM_TOLERANCE


def test_every_province_is_covered() -> None:
    assert len(PROVINCE_CODES) == 7


def test_sheets_and_types_are_declared_explicitly() -> None:
    # Scope is a deliberate choice, not an accident: three sheets, both types.
    assert TYPES == ("Actual", "Budget")
    assert len(SHEETS) == 3
    prefixes = [prefix for _, prefix in SHEETS]
    assert len(set(prefixes)) == len(prefixes), "indicator prefixes must be unique"
    for sheet, prefix in SHEETS:
        assert sheet.startswith("Provincial")
        assert prefix.startswith("FISCAL_PROV_")
