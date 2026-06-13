"""Tests for the in-pipeline data-quality gate (P1.S9). Pure logic — no network."""

from __future__ import annotations

from decimal import Decimal

from ingestion.common.quality import Candidate, run_quality_gate


def _c(code: str, unit: str, year: int, value: str, *, ind_id: int | None = 1,
       period_id: int | None = 10) -> Candidate:
    return Candidate(
        indicator_id=ind_id,
        indicator_code=code,
        unit_id=1,
        unit_code=unit,
        period_id=period_id,
        year=year,
        value=Decimal(value),
    )


def test_clean_batch_passes() -> None:
    batch = [
        _c("ADULT_LITERACY", "PCT", 2021, "67.9"),
        _c("GDP_GROWTH", "PCT", 2020, "-2.37"),
        _c("POP_TOTAL", "PERSONS", 2021, "29475010"),
        _c("LIFE_EXPECTANCY", "YEARS", 2021, "68.4"),
    ]
    result = run_quality_gate(batch)
    assert result.passed
    assert result.failures == []


def test_impossible_percentage_is_blocked() -> None:
    # The step's example: a 250% literacy rate must be caught.
    result = run_quality_gate([_c("ADULT_LITERACY", "PCT", 2021, "250")])
    assert not result.passed
    assert any("ADULT_LITERACY" in f and "250" in f for f in result.failures)


def test_implausible_growth_rate_is_blocked() -> None:
    result = run_quality_gate([_c("GDP_GROWTH", "PCT", 2020, "999")])
    assert not result.passed


def test_nonpositive_population_is_blocked() -> None:
    result = run_quality_gate([_c("POP_TOTAL", "PERSONS", 2021, "0")])
    assert not result.passed


def test_unresolved_reference_is_blocked() -> None:
    result = run_quality_gate([_c("GDP_USD", "USD", 2021, "12345", period_id=None)])
    assert not result.passed


def test_year_gaps_are_info_not_failure() -> None:
    batch = [
        _c("CPI_YOY", "PCT", 2018, "4.1"),
        _c("CPI_YOY", "PCT", 2020, "5.0"),  # 2019 missing
    ]
    result = run_quality_gate(batch)
    assert result.passed  # gaps never fail the gate
    assert any("CPI_YOY" in info and "missing" in info for info in result.infos)
