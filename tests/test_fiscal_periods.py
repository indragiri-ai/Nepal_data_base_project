"""Fiscal-year period tests (P2.S2). Run offline: no DB is hit.

These lock in the fiscal-year construction — the labels, the date-based sort_key
that interleaves with calendar years, and the exact Gregorian boundaries of a
real, independently-verified fiscal year (FY 2080/81). The boundary dates come
from the already-verified bs_calendar kernel, so this test uses the same source
of truth the loader does, without a database.
"""

from __future__ import annotations

from datetime import date, timedelta

from ingestion.common.bs_calendar import build_rows
from ingestion.common.fiscal_periods import (
    bs_fiscal_label,
    build_fiscal_period,
    gregorian_fiscal_label,
    sort_key_for_date,
    year_sort_key,
)


def test_labels() -> None:
    assert bs_fiscal_label(2080) == "2080/81"
    assert bs_fiscal_label(1999) == "1999/00"  # rolls the two-digit part
    assert gregorian_fiscal_label(date(2023, 7, 17), date(2024, 7, 15)) == "FY 2023/24"


def test_sort_key_interleaves_calendar_and_fiscal() -> None:
    """A fiscal year starting mid-2023 must sort strictly between calendar 2023
    and calendar 2024 — the property bare-year integers could not express."""
    cal_2023 = year_sort_key(2023)
    cal_2024 = year_sort_key(2024)
    fy_2080_81 = sort_key_for_date(date(2023, 7, 17))
    assert cal_2023 == 20230101
    assert cal_2024 == 20240101
    assert cal_2023 < fy_2080_81 < cal_2024


def test_fy_2080_81_matches_verified_boundaries() -> None:
    """FY 2080/81 = Shrawan 1 2080 .. Ashadh end 2081, i.e. 2023-07-17 .. 2024-07-15."""
    by_bs = {r[:3]: r[3] for r in build_rows()[0]}
    shrawan_2080 = by_bs[(2080, 4, 1)]  # verified: 2023-07-17
    shrawan_2081 = by_bs[(2081, 4, 1)]  # next fiscal year's start

    p = build_fiscal_period(2080, shrawan_2080, shrawan_2081)

    assert p.gregorian_start == date(2023, 7, 17)
    assert p.gregorian_end == shrawan_2081 - timedelta(days=1)
    # The year straddles two Gregorian years, mid-July to mid-July.
    assert p.gregorian_start.month == 7
    assert p.gregorian_end.month == 7
    assert p.gregorian_end.year == p.gregorian_start.year + 1
    assert p.bs_label == "2080/81"
    assert p.gregorian_label == "FY 2023/24"
    assert p.sort_key == 20230717
