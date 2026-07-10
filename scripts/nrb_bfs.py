"""NRB BFS staging review & promotion (staging-and-review workflow).

The human checkpoint between `nrb_bfs_staging` and the public warehouse:

    python scripts/nrb_bfs.py status
        Review queue: counts by status, months awaiting review, spot-check
        sample (two values to eyeball against the source file, per runbook).

    python scripts/nrb_bfs.py approve --all
    python scripts/nrb_bfs.py approve --month 2083-01
        Mark pending rows approved (record the review). --month is BS.

    python scripts/nrb_bfs.py reject --month 2083-01 --note "why"
        Mark pending rows of one month rejected, with a mandatory reason.

    python scripts/nrb_bfs.py promote
        Move APPROVED rows into `observations`: resolves dimensions, creates
        any missing BS-month time_periods from bs_calendar (true Gregorian
        dates — Blueprint §5.1), runs the quality gate, creates one release,
        loads change-aware (unchanged values skipped; changed values become
        revisions via the is_latest trigger), writes ingestion_log, marks
        staging rows 'promoted'. Idempotent.

Observations are loaded with status='provisional' — NRB's explanatory notes
say the monthly figures are provisional, based on unaudited BFI returns.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingestion.common.io_utf8 import configure_stdout_utf8  # noqa: E402
from ingestion.common.quality import Candidate, run_quality_gate  # noqa: E402
from ingestion.nrb.bfs_layout import BS_MONTH_CANONICAL  # noqa: E402

DATASET_NAME = "Banking and Financial Statistics (Monthly)"
SOURCE_NAME = "Nepal Rastra Bank"
GEOGRAPHY_CODE = "NP"

Cursor = psycopg.Cursor[Any]


def _scalar(cur: Cursor) -> Any:
    row = cur.fetchone()
    return None if row is None else row[0]


def connect() -> psycopg.Connection[Any]:
    load_dotenv()
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        raise SystemExit("DATABASE_URL is empty — fill it in .env first")
    return psycopg.connect(dsn)


def parse_bs_month(text: str) -> tuple[int, int]:
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", text.strip())
    if not m or not 1 <= int(m.group(2)) <= 12:
        raise SystemExit(f"--month must look like 2083-01 (BS year-month), got: {text!r}")
    return int(m.group(1)), int(m.group(2))


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def cmd_status(conn: psycopg.Connection[Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT review_status, count(*) FROM nrb_bfs_staging GROUP BY 1 ORDER BY 1"
        )
        counts = dict(cur.fetchall())
        print("Staging review queue:", counts or "empty")

        cur.execute(
            "SELECT bs_year, bs_month, count(*) FROM nrb_bfs_staging"
            " WHERE review_status = 'pending' GROUP BY 1, 2 ORDER BY 1, 2"
        )
        pending = cur.fetchall()
        if pending:
            months = ", ".join(f"{y}-{m:02d} ({n} rows)" for y, m, n in pending)
            print(f"Months awaiting review: {months}")
            # Spot-check sample (runbook: eyeball two values against the file).
            cur.execute(
                "SELECT bs_year, bs_month, row_label, bfi_class, value, source_url"
                " FROM nrb_bfs_staging WHERE review_status = 'pending'"
                " ORDER BY random() LIMIT 2"
            )
            print("Spot-check these against the source file before approving:")
            for y, m, label, cls, value, url in cur.fetchall():
                print(f"  {y}-{m:02d}  {label}  [{cls}] = {value}\n     source: {url}")
        else:
            print("Nothing pending.")


# ---------------------------------------------------------------------------
# approve / reject
# ---------------------------------------------------------------------------


def cmd_review(
    conn: psycopg.Connection[Any],
    new_status: str,
    month: str | None,
    approve_all: bool,
    note: str | None,
) -> None:
    if new_status == "rejected" and not note:
        raise SystemExit("reject requires --note explaining why (it goes on the record)")
    where, params = "review_status = 'pending'", []
    if month is not None:
        y, m = parse_bs_month(month)
        where += " AND bs_year = %s AND bs_month = %s"
        params = [y, m]
    elif not approve_all:
        raise SystemExit("pass --month 2083-01 or --all")
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE nrb_bfs_staging SET review_status = %s, review_note = %s,"  # noqa: S608
            f" reviewed_at = now() WHERE {where}",
            [new_status, note, *params],
        )
        print(f"{cur.rowcount} row(s) -> {new_status}.")
    conn.commit()


# ---------------------------------------------------------------------------
# promote
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StagedRow:
    id: int
    bs_year: int
    bs_month: int
    indicator_code: str
    bfi_class: str
    value: Decimal
    unit_code: str
    raw_ref: str


def ensure_month_period(cur: Cursor, bs_year: int, bs_month: int) -> tuple[int, date]:
    """Get-or-create the time_periods row for one BS month, with its true
    Gregorian dates from bs_calendar. Returns (period_id, gregorian_end)."""
    cur.execute(
        "SELECT min(gregorian_date), max(gregorian_date) FROM bs_calendar"
        " WHERE bs_year = %s AND bs_month = %s",
        (bs_year, bs_month),
    )
    row = cur.fetchone()
    if row is None or row[0] is None:
        raise SystemExit(
            f"bs_calendar has no days for BS {bs_year}-{bs_month:02d} —"
            " run `make load-calendar` (never guess dates)"
        )
    start, end = row
    bs_label = f"{BS_MONTH_CANONICAL[bs_month - 1]} {bs_year}"
    gregorian_label = f"Mid-{end.strftime('%b %Y')}"   # NRB's own phrasing
    sort_key = start.year * 10000 + start.month * 100 + start.day  # decision 0002
    cur.execute(
        "INSERT INTO time_periods"
        " (period_type, gregorian_start, gregorian_end, bs_label, gregorian_label, sort_key)"
        " VALUES ('month', %s, %s, %s, %s, %s)"
        " ON CONFLICT (period_type, gregorian_start, gregorian_end) DO UPDATE"
        "   SET bs_label = EXCLUDED.bs_label,"
        "       gregorian_label = EXCLUDED.gregorian_label,"
        "       sort_key = EXCLUDED.sort_key"
        " RETURNING id",
        (start, end, bs_label, gregorian_label, sort_key),
    )
    period_id = _scalar(cur)
    return int(period_id), end


def cmd_promote(conn: psycopg.Connection[Any]) -> None:  # noqa: PLR0915
    cur = conn.cursor()

    # --- Resolve fixed dimensions (fail loudly if reference data is missing) ---
    cur.execute(
        "SELECT d.id FROM datasets d JOIN sources s ON s.id = d.source_id"
        " WHERE d.name_en = %s AND s.name_en = %s",
        (DATASET_NAME, SOURCE_NAME),
    )
    dataset_id = _scalar(cur)
    if dataset_id is None:
        raise SystemExit("BFS dataset not found — run `make seed` first")
    cur.execute("SELECT id FROM geographies WHERE code = %s", (GEOGRAPHY_CODE,))
    geography_id = _scalar(cur)
    if geography_id is None:
        raise SystemExit("geography NP not found — run `make seed` first")
    cur.execute(
        "SELECT i.code, i.id, i.unit_id, u.code FROM indicators i"
        " JOIN units u ON u.id = i.unit_id WHERE i.code LIKE 'NRB_BFS_%'"
    )
    indicators = {code: (iid, unit_id, unit_code) for code, iid, unit_id, unit_code
                  in cur.fetchall()}
    if not indicators:
        raise SystemExit("no NRB_BFS_* indicators — run `make seed-nrb` first")

    cur.execute(
        "SELECT id, bs_year, bs_month, indicator_code, bfi_class, value, unit_code, raw_ref"
        " FROM nrb_bfs_staging WHERE review_status = 'approved'"
        " ORDER BY bs_year, bs_month, indicator_code, bfi_class"
    )
    staged = [StagedRow(*row) for row in cur.fetchall()]
    if not staged:
        print("Nothing approved to promote. (`status` shows the queue.)")
        return

    # A 'running' log row immediately, so a crash still leaves a trace.
    cur.execute(
        "INSERT INTO ingestion_log (dataset_id, status) VALUES (%s, 'running') RETURNING id",
        (dataset_id,),
    )
    log_id = _scalar(cur)
    conn.commit()

    loaded = unchanged = 0
    try:
        # --- Periods + candidates for the quality gate ---
        period_cache: dict[tuple[int, int], tuple[int, date]] = {}
        candidates: list[Candidate] = []
        for row in staged:
            key = (row.bs_year, row.bs_month)
            if key not in period_cache:
                period_cache[key] = ensure_month_period(cur, *key)
            period_id, greg_end = period_cache[key]
            ind = indicators.get(row.indicator_code)
            candidates.append(Candidate(
                indicator_id=None if ind is None else ind[0],
                indicator_code=row.indicator_code,
                unit_id=0 if ind is None else ind[1],
                unit_code=row.unit_code,
                period_id=period_id,
                year=greg_end.year,
                value=Decimal(row.value),
            ))

        gate = run_quality_gate(candidates)
        for info in gate.infos:
            print("  INFO:", info)
        if not gate.passed:
            raise RuntimeError("quality gate FAILED: " + "; ".join(gate.failures[:10]))

        # --- Release, then change-aware load with breakdowns ---
        cur.execute(
            "INSERT INTO releases (dataset_id, release_date, period_covered, raw_file_refs)"
            " VALUES (%s, CURRENT_DATE, %s, %s) RETURNING id",
            (
                dataset_id,
                f"BS {staged[0].bs_year}-{staged[0].bs_month:02d}"
                f" … {staged[-1].bs_year}-{staged[-1].bs_month:02d}",
                json.dumps(sorted({r.raw_ref for r in staged})),
            ),
        )
        release_id = _scalar(cur)

        promoted_ids: list[int] = []
        for row, candidate in zip(staged, candidates, strict=True):
            assert candidate.indicator_id is not None
            breakdowns = json.dumps({"bfi_class": row.bfi_class})
            cur.execute(
                "SELECT value FROM observations"
                " WHERE indicator_id = %s AND geography_id = %s AND time_period_id = %s"
                "   AND breakdowns = %s::jsonb AND is_latest",
                (candidate.indicator_id, geography_id, candidate.period_id, breakdowns),
            )
            current = _scalar(cur)
            if current is not None and Decimal(current) == candidate.value:
                unchanged += 1
            else:
                cur.execute(
                    "INSERT INTO observations"
                    " (indicator_id, geography_id, time_period_id, dataset_id, release_id,"
                    "  value, unit_id, breakdowns, status)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, 'provisional')",
                    (candidate.indicator_id, geography_id, candidate.period_id, dataset_id,
                     release_id, candidate.value, candidate.unit_id, breakdowns),
                )
                loaded += 1
            promoted_ids.append(row.id)

        cur.execute(
            "UPDATE nrb_bfs_staging SET review_status = 'promoted'"
            " WHERE id = ANY(%s)",
            (promoted_ids,),
        )
        cur.execute(
            "UPDATE ingestion_log SET status = 'success', finished_at = now(),"
            " release_id = %s, rows_in = %s, rows_loaded = %s, rows_rejected = 0"
            " WHERE id = %s",
            (release_id, len(staged), loaded, log_id),
        )
        conn.commit()
        print(
            f"Promoted {len(staged)} staged row(s): {loaded} loaded into observations,"
            f" {unchanged} unchanged (skipped — no spurious revision). Release {release_id}."
        )
    except Exception as exc:
        conn.rollback()
        with conn.cursor() as cur2:
            cur2.execute(
                "UPDATE ingestion_log SET status = 'failed', finished_at = now(),"
                " error_note = %s WHERE id = %s",
                (str(exc)[:2000], log_id),
            )
        conn.commit()
        raise SystemExit(f"promotion FAILED, nothing loaded: {exc}") from exc


def main() -> None:
    configure_stdout_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    for name in ("approve", "reject"):
        p = sub.add_parser(name)
        p.add_argument("--month", default=None, help="BS month, e.g. 2083-01")
        p.add_argument("--all", action="store_true", dest="all_rows")
        p.add_argument("--note", default=None)
    sub.add_parser("promote")
    args = parser.parse_args()

    with connect() as conn:
        if args.command == "status":
            cmd_status(conn)
        elif args.command == "approve":
            cmd_review(conn, "approved", args.month, args.all_rows, args.note)
        elif args.command == "reject":
            cmd_review(conn, "rejected", args.month, args.all_rows, args.note)
        elif args.command == "promote":
            cmd_promote(conn)


if __name__ == "__main__":
    main()
