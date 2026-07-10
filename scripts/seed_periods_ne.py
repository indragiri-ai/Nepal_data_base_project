"""Seed Nepali fiscal-year time periods (P2.S2).

Reads exact Shrawan-1 Gregorian dates from `bs_calendar` and seeds one
`time_periods` row per fiscal year (period_type='fiscal_year') into the SAME
table the World Bank calendar years already live in — each stored once with its
true Gregorian start/end (Blueprint §5.1). Idempotent: re-running changes no
counts.

It also realigns the existing calendar-year rows onto the date-based sort_key
scheme (YYYYMMDD; see docs/decisions/0002) so that a fiscal year, which starts
mid-year, sorts strictly between the two calendar years it falls within. This
touches only the `sort_key` ordering field — never a period's dates, labels, or
id, and nothing (no observation) references sort_key — so the World Bank periods
are unchanged in every meaningful sense.

Run with `make seed-periods-ne`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv

# Make the repo root importable when run as `python scripts/seed_periods_ne.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingestion.common.fiscal_periods import (  # noqa: E402
    FY_BS_FIRST,
    FY_BS_LAST,
    SHRAWAN,
    build_fiscal_period,
)
from ingestion.common.io_utf8 import configure_stdout_utf8  # noqa: E402

Cursor = psycopg.Cursor[Any]

# The date-based sort_key for a calendar-year row = its 1 January as YYYYMMDD.
YEAR_SORT_KEY_SQL = "extract(year from gregorian_start)::int * 10000 + 101"


def realign_year_sort_keys(cur: Cursor) -> int:
    """Move existing period_type='year' rows onto the YYYYMMDD sort_key scheme.
    Returns the number of rows actually changed (0 on a second run)."""
    cur.execute(
        f"UPDATE time_periods SET sort_key = {YEAR_SORT_KEY_SQL} "  # noqa: S608 — no user input
        f"WHERE period_type = 'year' "
        f"AND sort_key IS DISTINCT FROM {YEAR_SORT_KEY_SQL}"
    )
    return cur.rowcount


def load_shrawan_first_days(cur: Cursor, first_bs: int, last_bs: int) -> dict[int, Any]:
    """Return {bs_year: gregorian_date of Shrawan 1} for the requested BS years."""
    cur.execute(
        "SELECT bs_year, gregorian_date FROM bs_calendar "
        "WHERE bs_month = %s AND bs_day = 1 AND bs_year BETWEEN %s AND %s",
        (SHRAWAN, first_bs, last_bs),
    )
    return {int(bs_year): greg for bs_year, greg in cur.fetchall()}


def seed_fiscal_years(cur: Cursor) -> tuple[int, int, list[str]]:
    """Upsert fiscal-year rows for FY_BS_FIRST..FY_BS_LAST. Returns
    (rows_seeded, inserted, skipped_notes)."""
    # Need Shrawan 1 of each start year AND of the following year (for the end date).
    shrawan = load_shrawan_first_days(cur, FY_BS_FIRST, FY_BS_LAST + 1)

    cur.execute("SELECT count(*) FROM time_periods WHERE period_type = 'fiscal_year'")
    before = cur.fetchone()[0]  # type: ignore[index]

    seeded = 0
    skipped: list[str] = []
    for start_bs in range(FY_BS_FIRST, FY_BS_LAST + 1):
        this_shrawan = shrawan.get(start_bs)
        next_shrawan = shrawan.get(start_bs + 1)
        if this_shrawan is None or next_shrawan is None:
            # A boundary is missing from bs_calendar: report and skip, never guess.
            skipped.append(
                f"FY {start_bs}/{(start_bs + 1) % 100:02d}: "
                f"missing Shrawan-1 boundary in bs_calendar (never guessed)"
            )
            continue
        p = build_fiscal_period(start_bs, this_shrawan, next_shrawan)
        cur.execute(
            "INSERT INTO time_periods"
            " (period_type, gregorian_start, gregorian_end, bs_label, gregorian_label, sort_key)"
            " VALUES ('fiscal_year', %s, %s, %s, %s, %s)"
            " ON CONFLICT (period_type, gregorian_start, gregorian_end) DO UPDATE SET"
            "   bs_label = EXCLUDED.bs_label,"
            "   gregorian_label = EXCLUDED.gregorian_label,"
            "   sort_key = EXCLUDED.sort_key",
            (p.gregorian_start, p.gregorian_end, p.bs_label, p.gregorian_label, p.sort_key),
        )
        seeded += 1

    cur.execute("SELECT count(*) FROM time_periods WHERE period_type = 'fiscal_year'")
    after = cur.fetchone()[0]  # type: ignore[index]
    return seeded, after - before, skipped


def print_interleave_example(cur: Cursor) -> None:
    """Show, side by side and ordered by sort_key, that FY 2080/81 sits between
    calendar 2023 and 2024 with no collision — the whole point of P2.S2."""
    cur.execute(
        "SELECT period_type, gregorian_label, bs_label, gregorian_start, gregorian_end, sort_key"
        " FROM time_periods"
        " WHERE (period_type = 'year' AND gregorian_label IN ('2023', '2024'))"
        "    OR (period_type = 'fiscal_year' AND bs_label = '2080/81')"
        " ORDER BY sort_key"
    )
    rows = cur.fetchall()
    if not rows:
        print("  (no overlapping example rows found — is the calendar loaded?)")
        return
    print("\nInterleave check — ordered by sort_key (fiscal year sits between the calendars):")
    print(f"  {'type':12} {'label':11} {'bs':9} {'start':12} {'end':12} {'sort_key':>9}")
    for ptype, glabel, bslabel, start, end, key in rows:
        print(
            f"  {ptype:12} {glabel:11} {bslabel or '-':9} "
            f"{start!s:12} {end!s:12} {key:>9}"
        )


def main() -> int:
    configure_stdout_utf8()
    load_dotenv()
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print("FAILURE: DATABASE_URL is empty. Fill in .env (see .env.example).")
        return 1

    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM bs_calendar")
        if cur.fetchone()[0] == 0:  # type: ignore[index]
            print("FAILURE: bs_calendar is empty. Run `make load-calendar` first (P2.S1).")
            return 1

        realigned = realign_year_sort_keys(cur)
        seeded, inserted, skipped = seed_fiscal_years(cur)
        conn.commit()

        cur.execute("SELECT count(*) FROM time_periods WHERE period_type = 'year'")
        years = cur.fetchone()[0]  # type: ignore[index]
        cur.execute("SELECT count(*) FROM time_periods WHERE period_type = 'fiscal_year'")
        fiscal = cur.fetchone()[0]  # type: ignore[index]

        print(
            f"Fiscal-year periods: {seeded} upserted this run (inserted={inserted}).\n"
            f"Calendar-year rows realigned onto YYYYMMDD sort_key: {realigned}.\n"
            f"time_periods now: {years} calendar-year + {fiscal} fiscal-year rows."
        )
        if skipped:
            print("\nSkipped (boundary not in bs_calendar — NOT guessed):")
            for note in skipped:
                print(f"  - {note}")

        print_interleave_example(cur)

    print("\n(Re-run to confirm idempotency: inserted=0, realigned=0.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
