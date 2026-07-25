"""World Bank WDI ingestion pipeline (P1.S8).

For every indicator in our `indicators` table that has a `source_concept` (the
World Bank code), this pipeline:

  1. fetches the full Nepal series from the World Bank API v2 (handling paging);
  2. stores each raw API response in the raw lake BEFORE parsing (Blueprint §2.2);
  3. creates one `releases` row for the run (a vintage);
  4. parses observations, mapping WDI year -> our time_period, country -> Nepal,
     value -> numeric (null values are skipped and counted as rejected);
  5. loads observations under the release. It is CHANGE-AWARE: a value identical
     to the current latest is skipped (no spurious revision), so re-running on
     unchanged data keeps the row count stable. A genuinely changed value is
     inserted as a new row and the `is_latest` trigger demotes the old one;
  6. writes an `ingestion_log` row whether the run succeeds or fails;
  7. prints a plain-language summary.

Run with `make ingest-wb`. Idempotent: rerunning never creates duplicates.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import requests
from dotenv import load_dotenv

from ingestion.common.quality import Candidate, run_quality_gate
from ingestion.common.raw_lake import RawLake, RawLakeError

WB_URL = "https://api.worldbank.org/v2/country/{country}/indicator/{code}"
COUNTRY = "NPL"
GEOGRAPHY_CODE = "NP"
DATASET_NAME = "World Development Indicators"
PER_PAGE = "1000"
# Rows per executemany round trip. Large enough that 40k observations take tens
# of batches, small enough that one batch is a short, interruptible statement.
INSERT_BATCH_SIZE = 1000
# The continuity report has one line per series with a year gap — ~1,000 lines at
# full-catalogue scale, which would bury the summary. Print a sample, count the rest.
INFO_PRINT_LIMIT = 15
# Every quality failure is written here in full, so a blocked load is diagnosable
# without re-running the fetch (the console only shows the first ten).
GATE_REPORT = Path("reference/worldbank/quality_gate_failures.csv")


@dataclass(frozen=True)
class SeriesPoint:
    year: int
    value: float | None


def extract_points(rows: list[dict[str, Any]]) -> list[SeriesPoint]:
    """Pure parser (tested offline): turn WB data rows into year/value points."""
    points: list[SeriesPoint] = []
    for row in rows:
        date = row.get("date")
        if not isinstance(date, str):
            continue
        try:
            year = int(date)
        except ValueError:
            continue
        points.append(SeriesPoint(year=year, value=row.get("value")))
    return points


def fetch_series(wdi_code: str) -> tuple[list[SeriesPoint], bytes, str]:
    """Fetch the full Nepal series for one WDI code, following paging. Returns
    the parsed points, the raw bytes to archive, and the request URL."""
    url = WB_URL.format(country=COUNTRY, code=wdi_code)
    params = {"format": "json", "per_page": PER_PAGE}
    first = requests.get(url, params=params, timeout=60)
    first.raise_for_status()
    payload = first.json()
    if not isinstance(payload, list) or len(payload) < 2:
        raise RuntimeError(f"unexpected WB response for {wdi_code}: {payload!r:.200}")
    pages = int(payload[0].get("pages", 1))
    rows = list(payload[1] or [])
    raw_pages = [payload]
    for page in range(2, pages + 1):
        resp = requests.get(url, params={**params, "page": str(page)}, timeout=60)
        resp.raise_for_status()
        page_json = resp.json()
        rows.extend(page_json[1] or [])
        raw_pages.append(page_json)
    raw_bytes = first.content if pages == 1 else json.dumps(raw_pages).encode("utf-8")
    return extract_points(rows), raw_bytes, first.url


def _scalar(cur: psycopg.Cursor[Any]) -> Any:
    row = cur.fetchone()
    return None if row is None else row[0]


def _write_gate_report(failures: list[str]) -> None:
    """Write every quality-gate failure to a reviewable CSV. A blocked load must
    be diagnosable without re-running the whole fetch."""
    GATE_REPORT.parent.mkdir(parents=True, exist_ok=True)
    with GATE_REPORT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["failure"])
        writer.writerows([failure] for failure in failures)
    print(f"  wrote {len(failures)} quality-gate failure(s) to {GATE_REPORT}")


def clear_stale_pipeline_sessions(conn: psycopg.Connection[Any]) -> None:
    """Terminate 'idle in transaction' sessions left by a crashed pipeline run.

    Only our own pipelines write observations, so such a session is a dead
    predecessor still holding locks via the pooler — left alone it blocks this
    run into statement timeout (CLAUDE.md rule 8). Same idiom as
    `scripts/nrb_bfs.clear_stale_pipeline_sessions`.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pid, pg_terminate_backend(pid) FROM pg_stat_activity"
            " WHERE datname = current_database() AND pid <> pg_backend_pid()"
            "   AND state = 'idle in transaction'"
            "   AND query LIKE '%observations%'"
        )
        cleared = cur.fetchall()
    conn.commit()
    if cleared:
        print(f"  cleared {len(cleared)} stale lock-holding session(s) from a crashed run")


def archive_snapshot_with_retry(
    lake: RawLake, members: list[tuple[str, bytes, str]]
) -> list[str]:
    """Archive every fetched payload as ONE immutable snapshot, retrying blips.

    Writing one object per indicator meant ~4,000 Storage round trips and a
    ~3.8 h run on the free tier; a single snapshot is two uploads. Supabase
    Storage occasionally drops a connection, so we back off and retry — a blip
    on this one upload must not throw away a full fetch. Returns the snapshot's
    payload + metadata paths for releases.raw_file_refs.
    """
    last: Exception | None = None
    for attempt in range(4):
        try:
            stored = lake.store_snapshot("worldbank/wdi-catalogue", members)
            return [stored.payload_path, stored.metadata_path]
        except (requests.RequestException, RawLakeError) as exc:
            last = exc
            time.sleep(1.0 * (attempt + 1))
    raise last if last is not None else RuntimeError("unreachable")


def fetch_all_series(
    indicators: list[tuple[Any, ...]],
) -> tuple[dict[str, list[SeriesPoint]], list[tuple[str, bytes, str]], list[str]]:
    """Fetch every indicator's series with NO database connection open.

    This phase is minutes long at full-catalogue scale. Holding a connection
    across it is what leaves the 'idle in transaction' zombies that lock-block
    the next run, so the caller opens its connections around this, never during.

    Fetch only — the caller archives everything in one snapshot afterwards
    (raw-first still holds: nothing is loaded until the snapshot is stored).
    A per-indicator fetch failure is reported and skipped, never fatal — one bad
    indicator must not lose the other 1,395.

    Returns (points by WDI code, raw members for archiving, per-indicator
    failures). Each raw member is (wdi_code, raw_bytes, source_url).
    """
    points_by_code: dict[str, list[SeriesPoint]] = {}
    raw_members: list[tuple[str, bytes, str]] = []
    failures: list[str] = []
    total = len(indicators)
    for position, row in enumerate(indicators, start=1):
        wdi_code = row[4]
        try:
            points, raw_bytes, source_url = fetch_series(wdi_code)
        except (requests.RequestException, RuntimeError) as exc:
            failures.append(f"{wdi_code}: {exc}")
            continue
        points_by_code[wdi_code] = points
        raw_members.append((wdi_code, raw_bytes, source_url))
        if position % 100 == 0 or position == total:
            print(f"  ... fetched {position}/{total} indicators ({len(failures)} failed)")
    return points_by_code, raw_members, failures


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest World Bank WDI series for Nepal.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="fetch and archive raw, run the quality gate, report what WOULD be"
        " loaded — but write no release and no observations",
    )
    args = parser.parse_args(argv)
    dry_run: bool = args.dry_run

    load_dotenv()
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        print("FAILURE: DATABASE_URL is empty. Fill in .env.")
        return 1
    # A dry run loads nothing, so it must not write raw-lake objects either
    # (~4,000 storage round trips thrown away). The real run archives raw-first.
    lake = None if dry_run else RawLake.from_env()

    # --- Phase 1 (short connection): read reference data, open the log row -----
    # The connection is CLOSED before the long network phase. Holding it open
    # across minutes of HTTP is what leaves 'idle in transaction' zombies on
    # Supabase's pooler, which then lock-block the next run (CLAUDE.md rule 8).
    conn = psycopg.connect(db_url, connect_timeout=30)
    clear_stale_pipeline_sessions(conn)
    cur = conn.cursor()

    cur.execute("SELECT id FROM datasets WHERE name_en = %s", (DATASET_NAME,))
    dataset_id = _scalar(cur)
    cur.execute("SELECT id FROM geographies WHERE code = %s", (GEOGRAPHY_CODE,))
    geography_id = _scalar(cur)
    if dataset_id is None or geography_id is None:
        print("FAILURE: reference data missing. Run `make seed` first.")
        conn.close()
        return 1

    # A crashed prior run leaves its log row stuck at 'running' forever (the
    # crash happens in the connection-less fetch phase, so its own except block
    # never runs). Close them out so the log reflects reality.
    cur.execute(
        "UPDATE ingestion_log SET status = 'failed', finished_at = now(),"
        " error_note = 'orphaned running row closed by a later run'"
        " WHERE dataset_id = %s AND status = 'running'",
        (dataset_id,),
    )
    if cur.rowcount:
        print(f"  closed {cur.rowcount} orphaned 'running' log row(s) from a crashed run")

    cur.execute("SELECT gregorian_label, id FROM time_periods WHERE period_type = 'year'")
    year_to_period = {int(label): pid for label, pid in cur.fetchall()}
    # Scope to World Bank indicators only. Other pipelines (NRB, census) also set
    # source_concept, but with THEIR concept codes (e.g. 'BFS.C4.ccdratio',
    # 'population/highlight:density') — not WDI codes. Sending those to the WB API
    # wastes a request each and, worse, would load a wrong value under the WDI
    # dataset if a foreign concept ever collided with a real WDI code. We scope on
    # origin_source_id (immutable provenance — this dataset's source), NOT on
    # preferred_source_id: decision 0005 repoints the preferred source of the
    # census/WB collision series to the census, and those WB series must keep being
    # refreshed here.
    cur.execute(
        "SELECT i.code, i.id, i.unit_id, u.code, i.source_concept"
        " FROM indicators i JOIN units u ON u.id = i.unit_id"
        " WHERE i.source_concept IS NOT NULL"
        "   AND i.origin_source_id = (SELECT source_id FROM datasets WHERE id = %s)"
        " ORDER BY i.code",
        (dataset_id,),
    )
    indicators = cur.fetchall()

    # Preload current latest values so we only write genuine new/changed numbers.
    cur.execute(
        "SELECT indicator_id, time_period_id, value FROM observations"
        " WHERE geography_id = %s AND is_latest AND breakdowns = '{}'::jsonb",
        (geography_id,),
    )
    latest: dict[tuple[int, int], Decimal] = {
        (ind, per): val for ind, per, val in cur.fetchall()
    }

    # Persist a 'running' log row immediately so a crash still leaves a trace.
    cur.execute(
        "INSERT INTO ingestion_log (dataset_id, status) VALUES (%s, 'running') RETURNING id",
        (dataset_id,),
    )
    log_id = _scalar(cur)
    conn.commit()
    conn.close()

    # --- Phase 2 (NO connection open): fetch every series, then archive raw ---
    print(f"Fetching {len(indicators)} indicator series from the World Bank...")
    points_by_code, raw_members, fetch_failures = fetch_all_series(indicators)
    for failure in fetch_failures[:10]:
        print(f"  [fetch failed] {failure}")

    # Archive all fetched payloads as ONE immutable snapshot (raw-first: done
    # before any observation is written). A dry run (lake is None) skips this.
    raw_refs: list[str] = []
    if lake is not None and raw_members:
        print(f"Archiving {len(raw_members)} raw payloads as one immutable snapshot...")
        try:
            raw_refs = archive_snapshot_with_retry(lake, raw_members)
        except (requests.RequestException, RawLakeError, RuntimeError) as exc:
            # Raw-first (rule #3): if the payload cannot be archived we must not
            # load. Mark the log failed and stop cleanly — no observations written.
            conn = psycopg.connect(db_url, connect_timeout=30)
            with conn.cursor() as fail_cur:
                fail_cur.execute(
                    "UPDATE ingestion_log SET status = 'failed', finished_at = now(),"
                    " error_note = %s WHERE id = %s",
                    (f"raw archive failed, nothing loaded: {exc}", log_id),
                )
            conn.commit()
            conn.close()
            print(f"FAILURE: raw archive failed after retries — nothing loaded. {exc}")
            return 1

    # --- Phase 3 (short connection): gate, then load in batches ---------------
    rows_in = loaded = rejected = unchanged = 0
    release_id: int | None = None
    conn = psycopg.connect(db_url, connect_timeout=30)
    cur = conn.cursor()
    try:
        candidates: list[Candidate] = []
        for indicator_code, indicator_id, unit_id, unit_code, wdi_code in indicators:
            for point in points_by_code.get(wdi_code, []):
                rows_in += 1
                if point.value is None:
                    rejected += 1
                    continue
                period_id = year_to_period.get(point.year)
                if period_id is None:
                    rejected += 1
                    continue
                candidates.append(
                    Candidate(
                        indicator_id=indicator_id,
                        indicator_code=indicator_code,
                        unit_id=unit_id,
                        unit_code=unit_code,
                        period_id=period_id,
                        year=point.year,
                        value=Decimal(str(point.value)),
                    )
                )

        # --- Quality gate: must pass BEFORE any release/observation is written ---
        result = run_quality_gate(candidates)
        # At catalogue scale the continuity report is ~1,000 lines; summarise it.
        for info in result.infos[:INFO_PRINT_LIMIT]:
            print(f"  [info] {info}")
        if len(result.infos) > INFO_PRINT_LIMIT:
            print(f"  [info] ... and {len(result.infos) - INFO_PRINT_LIMIT} more series"
                  " with year gaps (WB simply has no value for those years)")
        if result.failures:
            _write_gate_report(result.failures)
        if not result.passed:
            reason = f"{len(result.failures)} quality failure(s): " + "; ".join(result.failures[:5])
            cur.execute(
                "UPDATE ingestion_log SET status = 'failed', finished_at = now(),"
                " rows_in = %s, rows_loaded = 0, rows_rejected = %s, error_note = %s"
                " WHERE id = %s",
                (rows_in, rejected, reason[:1000], log_id),
            )
            conn.commit()
            conn.close()
            print(f"QUALITY GATE BLOCKED THE LOAD — nothing was written."
                  f" {len(result.failures)} failure(s), full list in {GATE_REPORT}. First 10:")
            for failure in result.failures[:10]:
                print(f"  - {failure}")
            return 1

        if dry_run:
            cur.execute(
                "UPDATE ingestion_log SET status = 'success', finished_at = now(),"
                " rows_in = %s, rows_loaded = 0, rows_rejected = %s, error_note = %s"
                " WHERE id = %s",
                (rows_in, rejected, "dry run — nothing written", log_id),
            )
            conn.commit()
            conn.close()
            would_load = 0
            for c in candidates:
                assert c.indicator_id is not None and c.period_id is not None
                if latest.get((c.indicator_id, c.period_id)) != c.value:
                    would_load += 1
            print("\nDRY RUN — the quality gate PASSED and nothing was written.")
            print(f"  indicators fetched : {len(indicators) - len(fetch_failures)}"
                  f"/{len(indicators)}")
            print(f"  data points read   : {rows_in}")
            print(f"  would load         : {would_load} observations")
            print(f"  would skip (same)  : {len(candidates) - would_load}")
            print(f"  rejected (nulls etc): {rejected}")
            print("Re-run without --dry-run to load.")
            return 0

        # --- Gate passed: create the release and load new/changed values ---
        cur.execute(
            "INSERT INTO releases (dataset_id, release_date)"
            " VALUES (%s, CURRENT_DATE) RETURNING id",
            (dataset_id,),
        )
        release_id = _scalar(cur)

        # Batched with executemany in chunks: at full-catalogue scale this is
        # tens of thousands of rows, and Supabase's free tier drops the
        # connection under sustained row-by-row writes (CLAUDE.md rule 8).
        to_insert: list[tuple[Any, ...]] = []
        for candidate in candidates:
            assert candidate.indicator_id is not None and candidate.period_id is not None
            if latest.get((candidate.indicator_id, candidate.period_id)) == candidate.value:
                unchanged += 1
                continue
            to_insert.append(
                (candidate.indicator_id, geography_id, candidate.period_id, dataset_id,
                 release_id, candidate.value, candidate.unit_id)
            )

        insert_sql = (
            "INSERT INTO observations"
            " (indicator_id, geography_id, time_period_id, dataset_id,"
            "  release_id, value, unit_id, status)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, 'final')"
        )
        for start in range(0, len(to_insert), INSERT_BATCH_SIZE):
            batch = to_insert[start : start + INSERT_BATCH_SIZE]
            cur.executemany(insert_sql, batch)
            loaded += len(batch)
            if len(to_insert) > INSERT_BATCH_SIZE:
                print(f"  ... inserted {loaded}/{len(to_insert)} observations")

        cur.execute(
            "UPDATE releases SET raw_file_refs = %s WHERE id = %s",
            (json.dumps(raw_refs), release_id),
        )
        cur.execute(
            "UPDATE ingestion_log SET status = 'success', finished_at = now(),"
            " rows_in = %s, rows_loaded = %s, rows_rejected = %s,"
            " raw_file_refs = %s, release_id = %s, error_note = %s WHERE id = %s",
            (rows_in, loaded, rejected, json.dumps(raw_refs), release_id,
             f"unchanged={unchanged}; fetch_failed={len(fetch_failures)}", log_id),
        )
        conn.commit()
    except Exception as exc:  # noqa: BLE001 — any failure must be logged, then surfaced
        conn.rollback()
        cur.execute(
            "UPDATE ingestion_log SET status = 'failed', finished_at = now(),"
            " error_note = %s WHERE id = %s",
            (str(exc), log_id),
        )
        conn.commit()
        conn.close()
        print(f"FAILURE: ingestion failed and was logged. Reason: {exc}")
        return 1

    conn.close()
    print("World Bank ingestion summary:")
    print(f"  indicators fetched : {len(indicators) - len(fetch_failures)}/{len(indicators)}")
    print(f"  data points read   : {rows_in}")
    print(f"  observations loaded: {loaded}")
    print(f"  unchanged (skipped): {unchanged}")
    print(f"  rejected (nulls etc): {rejected}")
    print("  quality gate       : PASSED")
    print(f"  release id         : {release_id}")
    if fetch_failures:
        print(f"\n  {len(fetch_failures)} indicator(s) could not be fetched — reported, not"
              " guessed. Re-run to retry just those:")
        for failure in fetch_failures:
            print(f"    - {failure}")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
