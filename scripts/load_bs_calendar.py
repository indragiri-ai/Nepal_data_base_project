"""Load the BS<->AD day-level calendar into bs_calendar (P2.S1).

Thin CLI over the pure expansion kernel in `ingestion.common.bs_calendar`: it
builds the ~36,500 daily rows and upserts them idempotently — re-running produces
the identical table with no new rows. The dates are cross-checked against two
public converters after load (see reference/calendar/PROVENANCE.md).

Run with `make load-calendar`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv

# Make the repo root importable when run as `python scripts/load_bs_calendar.py`
# (sys.path[0] is scripts/, so the top-level `ingestion` package isn't found).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingestion.common.bs_calendar import DATA_FILE, CalendarRow, build_rows  # noqa: E402
from ingestion.common.io_utf8 import configure_stdout_utf8  # noqa: E402


def load(cur: psycopg.Cursor[Any], rows: list[CalendarRow]) -> tuple[int, int]:
    """Idempotent upsert via a COPY-staged temp table. Returns (inserted, updated)."""
    cur.execute("SELECT count(*) FROM bs_calendar")
    before = cur.fetchone()[0]  # type: ignore[index]

    cur.execute(
        "CREATE TEMP TABLE _bs_stage "
        "(bs_year smallint, bs_month smallint, bs_day smallint, "
        " gregorian_date date, weekday smallint) ON COMMIT DROP"
    )
    with cur.copy(
        "COPY _bs_stage (bs_year, bs_month, bs_day, gregorian_date, weekday) FROM STDIN"
    ) as cp:
        for row in rows:
            cp.write_row(row)

    # Upsert: unchanged rows are untouched (idempotent); a corrected source value
    # would self-heal. The WHERE skips rows whose values already match, so
    # rowcount counts only real writes.
    cur.execute(
        """
        INSERT INTO bs_calendar (bs_year, bs_month, bs_day, gregorian_date, weekday)
        SELECT bs_year, bs_month, bs_day, gregorian_date, weekday FROM _bs_stage
        ON CONFLICT (bs_year, bs_month, bs_day) DO UPDATE
            SET gregorian_date = EXCLUDED.gregorian_date,
                weekday        = EXCLUDED.weekday,
                updated_at     = now()
        WHERE bs_calendar.gregorian_date IS DISTINCT FROM EXCLUDED.gregorian_date
           OR bs_calendar.weekday        IS DISTINCT FROM EXCLUDED.weekday
        """
    )
    affected = cur.rowcount  # inserts + real updates (unchanged rows excluded)
    cur.execute("SELECT count(*) FROM bs_calendar")
    after = cur.fetchone()[0]  # type: ignore[index]
    inserted = after - before
    return inserted, affected - inserted


def main() -> int:
    configure_stdout_utf8()
    load_dotenv()
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print("FAILURE: DATABASE_URL is empty. Fill in .env (see .env.example).")
        return 1
    if not DATA_FILE.exists():
        print(f"FAILURE: {DATA_FILE} not found (see reference/calendar/PROVENANCE.md).")
        return 1

    rows, meta = build_rows()
    fy, fm, fd, fg, _ = meta["first"]
    ly, lm, ld, lg, _ = meta["last"]
    print(
        f"Expanded {meta['count']} Nepali days from the month-length table.\n"
        f"  BS {fy}-{fm:02d}-{fd:02d} = AD {fg}  ->  BS {ly}-{lm:02d}-{ld:02d} = AD {lg}"
    )

    with psycopg.connect(url) as conn, conn.cursor() as cur:
        inserted, updated = load(cur, rows)
        conn.commit()
        cur.execute("SELECT count(*) FROM bs_calendar")
        total = cur.fetchone()[0]  # type: ignore[index]

    print(f"Loaded. inserted={inserted} updated={updated} total_rows={total}")
    print("(Re-run to confirm idempotency: inserted=0 updated=0.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
