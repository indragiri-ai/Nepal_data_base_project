"""BS<->AD calendar expansion (P2.S1) — the pure, DB-free kernel.

Reads the authoritative month-length table + anchor from
reference/calendar/bs_month_lengths.json (see reference/calendar/PROVENANCE.md)
and walks it day by day, giving each Bikram Sambat date its exact Gregorian date
and weekday. This module holds no I/O to the database, so it is unit-tested
offline; `scripts/load_bs_calendar.py` is the thin CLI that loads the result.

We never *compute* the irregular BS month lengths — those are authoritative facts
from the JSON. All we do here is count days forward from the anchor.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

DATA_FILE = Path("reference/calendar/bs_month_lengths.json")

# 1-indexed BS month names, for readable output elsewhere.
BS_MONTHS_EN = [
    "",
    "Baisakh", "Jestha", "Ashadh", "Shrawan", "Bhadra", "Ashwin",
    "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra",
]
WEEKDAYS_EN = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

# One expanded day: (bs_year, bs_month, bs_day, gregorian_date, weekday[0=Sun]).
CalendarRow = tuple[int, int, int, date, int]


def weekday_sun0(d: date) -> int:
    """Weekday with 0=Sunday..6=Saturday (the Nepali week convention)."""
    return d.isoweekday() % 7  # isoweekday: Mon=1..Sun=7 -> Sun=0..Sat=6


def build_rows(data_file: Path = DATA_FILE) -> tuple[list[CalendarRow], dict[str, Any]]:
    """Expand the month-length table into one row per Nepali day."""
    spec = json.loads(data_file.read_text(encoding="utf-8"))
    anchor_bs = tuple(spec["anchor_bs"])  # (year, 1, 1)
    ay, am, ad = spec["anchor_ad"]
    greg = date(ay, am, ad)
    lengths: dict[str, list[int]] = spec["month_lengths"]

    rows: list[CalendarRow] = []
    for year in range(spec["bs_year_min"], spec["bs_year_max"] + 1):
        months = lengths[str(year)]
        for month_idx, month_len in enumerate(months, start=1):
            for day in range(1, month_len + 1):
                rows.append((year, month_idx, day, greg, weekday_sun0(greg)))
                greg += timedelta(days=1)

    # Sanity: the very first row must be the anchor itself.
    assert rows[0][:3] == anchor_bs, (rows[0], anchor_bs)
    meta = {
        "anchor_bs": anchor_bs,
        "anchor_ad": (ay, am, ad),
        "first": rows[0],
        "last": rows[-1],
        "count": len(rows),
    }
    return rows, meta
