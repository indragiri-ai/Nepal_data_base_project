"""BS calendar expansion tests (P2.S1). Run offline: no DB is hit.

These lock in the calendar kernel — the anchor, a couple of independently-verified
real dates, and the bijection property (every AD day maps to exactly one BS day).
If the month-length source data ever drifts, these fail loudly.
"""

from __future__ import annotations

from datetime import date, timedelta

from ingestion.common.bs_calendar import build_rows


def test_anchor_is_first_row() -> None:
    rows, meta = build_rows()
    assert rows[0][:3] == (2000, 1, 1)
    assert rows[0][3] == date(1943, 4, 14)  # anchor: BS 2000-01-01 = AD 1943-04-14
    assert meta["count"] == len(rows)


def test_known_dates_match_public_converters() -> None:
    """Dates independently confirmed against two public converters (see PROVENANCE)."""
    by_bs = {r[:3]: r[3] for r in build_rows()[0]}
    # Nepali New Year 2080 (Baisakh 1) = Fri 14 Apr 2023.
    assert by_bs[(2080, 1, 1)] == date(2023, 4, 14)
    # Shrawan 1, 2080 = start of fiscal year 2080/81 = 17 Jul 2023 (mid-July boundary).
    assert by_bs[(2080, 4, 1)] == date(2023, 7, 17)


def test_gregorian_dates_are_a_contiguous_bijection() -> None:
    """Every Nepali day maps to a distinct AD day, with no gaps or overlaps."""
    greg = [r[3] for r in build_rows()[0]]
    assert len(greg) == len(set(greg))  # distinct
    assert greg == sorted(greg)  # monotonic
    # contiguous: last - first + 1 == count
    assert (greg[-1] - greg[0]) == timedelta(days=len(greg) - 1)
