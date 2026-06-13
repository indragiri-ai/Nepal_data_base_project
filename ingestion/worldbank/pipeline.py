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

import json
import os
import sys
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import psycopg
import requests
from dotenv import load_dotenv

from ingestion.common.quality import Candidate, run_quality_gate
from ingestion.common.raw_lake import RawLake

WB_URL = "https://api.worldbank.org/v2/country/{country}/indicator/{code}"
COUNTRY = "NPL"
GEOGRAPHY_CODE = "NP"
DATASET_NAME = "World Development Indicators"
PER_PAGE = "1000"


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


def run() -> int:
    load_dotenv()
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        print("FAILURE: DATABASE_URL is empty. Fill in .env.")
        return 1
    lake = RawLake.from_env()

    conn = psycopg.connect(db_url)
    cur = conn.cursor()

    cur.execute("SELECT id FROM datasets WHERE name_en = %s", (DATASET_NAME,))
    dataset_id = _scalar(cur)
    cur.execute("SELECT id FROM geographies WHERE code = %s", (GEOGRAPHY_CODE,))
    geography_id = _scalar(cur)
    if dataset_id is None or geography_id is None:
        print("FAILURE: reference data missing. Run `make seed` first.")
        conn.close()
        return 1

    cur.execute("SELECT gregorian_label, id FROM time_periods WHERE period_type = 'year'")
    year_to_period = {int(label): pid for label, pid in cur.fetchall()}
    cur.execute(
        "SELECT i.code, i.id, i.unit_id, u.code, i.source_concept"
        " FROM indicators i JOIN units u ON u.id = i.unit_id"
        " WHERE i.source_concept IS NOT NULL ORDER BY i.code"
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

    rows_in = loaded = rejected = unchanged = 0
    raw_refs: list[str] = []
    release_id: int | None = None
    try:
        # --- Fetch + archive raw + build candidate observations ---
        candidates: list[Candidate] = []
        for indicator_code, indicator_id, unit_id, unit_code, wdi_code in indicators:
            points, raw_bytes, source_url = fetch_series(wdi_code)
            stored = lake.store(f"worldbank/wdi/{wdi_code}", raw_bytes, source_url)
            raw_refs.append(stored.payload_path)
            for point in points:
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
        for info in result.infos:
            print(f"  [info] {info}")
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
            print("QUALITY GATE BLOCKED THE LOAD — nothing was written. Reasons:")
            for failure in result.failures[:10]:
                print(f"  - {failure}")
            return 1

        # --- Gate passed: create the release and load new/changed values ---
        cur.execute(
            "INSERT INTO releases (dataset_id, release_date)"
            " VALUES (%s, CURRENT_DATE) RETURNING id",
            (dataset_id,),
        )
        release_id = _scalar(cur)
        for candidate in candidates:
            assert candidate.indicator_id is not None and candidate.period_id is not None
            if latest.get((candidate.indicator_id, candidate.period_id)) == candidate.value:
                unchanged += 1
                continue
            cur.execute(
                "INSERT INTO observations"
                " (indicator_id, geography_id, time_period_id, dataset_id,"
                "  release_id, value, unit_id, status)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, 'final')",
                (candidate.indicator_id, geography_id, candidate.period_id, dataset_id,
                 release_id, candidate.value, candidate.unit_id),
            )
            loaded += 1

        cur.execute(
            "UPDATE releases SET raw_file_refs = %s WHERE id = %s",
            (json.dumps(raw_refs), release_id),
        )
        cur.execute(
            "UPDATE ingestion_log SET status = 'success', finished_at = now(),"
            " rows_in = %s, rows_loaded = %s, rows_rejected = %s,"
            " raw_file_refs = %s, release_id = %s, error_note = %s WHERE id = %s",
            (rows_in, loaded, rejected, json.dumps(raw_refs), release_id,
             f"unchanged={unchanged}", log_id),
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
    print(f"  indicators fetched : {len(indicators)}")
    print(f"  data points read   : {rows_in}")
    print(f"  observations loaded: {loaded}")
    print(f"  unchanged (skipped): {unchanged}")
    print(f"  rejected (nulls etc): {rejected}")
    print("  quality gate       : PASSED")
    print(f"  release id         : {release_id}")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
