"""Fiscal-year period construction (P2.S2) — the pure, DB-free kernel.

A Nepali fiscal year runs from Shrawan 1 to the last day of Ashadh in the next
BS year (~mid-July to mid-July). We NEVER guess the boundary dates: the exact
Gregorian start/end come from the loaded `bs_calendar` (Blueprint §5.1 — no
formula conversion). This module turns a pair of exact Shrawan-1 dates into a
`time_periods` row (labels, sort_key, dates); the database I/O lives in
`scripts/seed_periods_ne.py`, so this logic is unit-tested offline.

sort_key convention (see docs/decisions/0002): every period, of every type, is
ordered by its Gregorian start encoded as an integer YYYYMMDD. This is the one
monotonic timeline key that lets a fiscal year (starting mid-year) sort strictly
between the two calendar years it falls within — impossible with the bare-year
integers Phase 1 used. It fits `integer` (20991231 < 2.1e9).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

# Data era: mirror the calendar-year coverage seeded in Phase 1 (1960-2030 AD).
# Shrawan 1 of BS 2017 is ~mid-July 1960; FY 2086/87 ends ~mid-July 2030. Both
# boundaries live in bs_calendar (BS 2000-2099), so nothing is extrapolated.
FY_BS_FIRST = 2017
FY_BS_LAST = 2086

# The fiscal year starts on the 1st of Shrawan, the 4th month of the BS calendar.
SHRAWAN = 4


@dataclass(frozen=True)
class FiscalPeriod:
    """One fiscal-year row, ready to upsert into time_periods."""

    start_bs_year: int
    gregorian_start: date
    gregorian_end: date
    bs_label: str
    gregorian_label: str
    sort_key: int


def sort_key_for_date(d: date) -> int:
    """A period's Gregorian start as an integer YYYYMMDD — one monotonic key for
    the whole timeline, so mixed period types interleave in true date order."""
    return d.year * 10_000 + d.month * 100 + d.day


def year_sort_key(year: int) -> int:
    """The date-based sort_key a calendar-year period gets (its 1 January)."""
    return sort_key_for_date(date(year, 1, 1))


def bs_fiscal_label(start_bs_year: int) -> str:
    """e.g. 2080 -> '2080/81' (Shrawan 2080 -> Ashadh 2081)."""
    return f"{start_bs_year}/{(start_bs_year + 1) % 100:02d}"


def gregorian_fiscal_label(start: date, end: date) -> str:
    """e.g. 2023-07-17 .. 2024-07-15 -> 'FY 2023/24'."""
    return f"FY {start.year}/{end.year % 100:02d}"


def build_fiscal_period(
    start_bs_year: int, shrawan1_this: date, shrawan1_next: date
) -> FiscalPeriod:
    """Assemble the fiscal year from two exact Shrawan-1 dates.

    The end is the day *before* next year's Shrawan 1 — i.e. the last day of
    Ashadh — taken from the calendar, never approximated as 'mid-July'.
    """
    gregorian_end = shrawan1_next - timedelta(days=1)
    return FiscalPeriod(
        start_bs_year=start_bs_year,
        gregorian_start=shrawan1_this,
        gregorian_end=gregorian_end,
        bs_label=bs_fiscal_label(start_bs_year),
        gregorian_label=gregorian_fiscal_label(shrawan1_this, gregorian_end),
        sort_key=sort_key_for_date(shrawan1_this),
    )
