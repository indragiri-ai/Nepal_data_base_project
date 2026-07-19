"""Census 2021 ingestion pipeline (NSO onboarding).

For Nepal and every seeded province (7) and district (77), this pipeline:

  1. fetches /population/highlight and /literacy from the NSO census API with
     the geography's own NSO ids (reference/census/nso_geo_ids.csv — provenance
     in reference/census/PROVENANCE.md);
  2. stores every raw response in the raw lake BEFORE parsing;
  3. parses via the pure census_layout parsers (unknown shapes fail loudly);
  4. runs the quality gate BEFORE anything is written;
  5. creates one `releases` row and loads observations under it, CHANGE-AWARE
     per (indicator, geography, period, breakdowns) so re-runs never duplicate
     and a revised value inserts a new row for the is_latest trigger to demote;
  6. writes `ingestion_log` either way.

Values land on the calendar-year 2021 period with status='final' (the portal
serves NSO's published final results). Run with `make ingest-census`.
"""

from __future__ import annotations

import json
import os
import sys
import time
from csv import DictReader
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import requests
from dotenv import load_dotenv

from ingestion.common.io_utf8 import configure_stdout_utf8
from ingestion.common.quality import Candidate, run_quality_gate
from ingestion.common.raw_lake import RawLake
from ingestion.nso.census_layout import (
    CENSUS_YEAR,
    ParsedValue,
    parse_highlight,
    parse_literacy,
)

API_BASE = "https://censusapi.cbs.gov.np/api/v1"
GEO_IDS_CSV = Path("reference/census/nso_geo_ids.csv")
DATASET_NAME = "National Population and Housing Census 2021"
ENDPOINTS = (
    ("population/highlight", parse_highlight),
    ("literacy", parse_literacy),
)
BATCH = 200  # executemany batch size — Supabase free tier dislikes row-by-row


@dataclass(frozen=True)
class GeoTarget:
    our_code: str
    params: dict[str, str]  # NSO query params ({} = national)


def load_geo_targets() -> list[GeoTarget]:
    """National + every seeded province/district, with their NSO API ids."""
    targets = [GeoTarget("NP", {})]
    with GEO_IDS_CSV.open(encoding="utf-8", newline="") as fh:
        for r in DictReader(fh):
            if r["level"] == "province":
                targets.append(GeoTarget(r["our_code"], {"province": r["nso_province"]}))
            elif r["level"] == "district":
                targets.append(
                    GeoTarget(
                        r["our_code"],
                        {"province": r["nso_province"], "district": r["nso_district"]},
                    )
                )
    return targets


def fetch_json(url: str, params: dict[str, str]) -> tuple[dict[str, Any], bytes, str]:
    """GET with one retry (the API is occasionally slow, never paginated)."""
    last: Exception | None = None
    for attempt in (1, 2):
        try:
            resp = requests.get(url, params=params, timeout=60)
            resp.raise_for_status()
            return resp.json(), resp.content, resp.url
        except (requests.RequestException, ValueError) as exc:
            last = exc
            if attempt == 1:
                time.sleep(2)
    raise RuntimeError(f"census API failed twice for {url} {params}: {last}")


def _scalar(cur: psycopg.Cursor[Any]) -> Any:
    row = cur.fetchone()
    return None if row is None else row[0]


def run() -> int:
    configure_stdout_utf8()
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
    cur.execute(
        "SELECT gregorian_label, id FROM time_periods"
        " WHERE period_type = 'year' AND gregorian_label = %s",
        (str(CENSUS_YEAR),),
    )
    row = cur.fetchone()
    period_id = row[1] if row else None
    cur.execute(
        "SELECT i.code, i.id, i.unit_id, u.code FROM indicators i"
        " JOIN units u ON u.id = i.unit_id WHERE i.code LIKE 'CENSUS_%'"
    )
    indicator_info = {
        code: (iid, unit_id, unit_code) for code, iid, unit_id, unit_code in cur.fetchall()
    }
    cur.execute("SELECT code, id FROM geographies")
    geo_ids: dict[str, int] = dict(cur.fetchall())

    if dataset_id is None or period_id is None or not indicator_info:
        print("FAILURE: reference data missing — run `make seed` and `make seed-census` first.")
        conn.close()
        return 1

    targets = load_geo_targets()
    missing_geos = [t.our_code for t in targets if t.our_code not in geo_ids]
    if missing_geos:
        print(f"FAILURE: geographies not seeded: {missing_geos[:5]} — run `make seed`.")
        conn.close()
        return 1

    # Current latest values per full cell so we only write genuine changes.
    cur.execute(
        "SELECT indicator_id, geography_id, breakdowns::text, value FROM observations o"
        " WHERE o.is_latest AND o.time_period_id = %s AND o.dataset_id = %s",
        (period_id, dataset_id),
    )
    latest: dict[tuple[int, int, str], Decimal] = {
        (i, g, b): v for i, g, b, v in cur.fetchall()
    }

    cur.execute(
        "INSERT INTO ingestion_log (dataset_id, status) VALUES (%s, 'running') RETURNING id",
        (dataset_id,),
    )
    log_id = _scalar(cur)
    conn.commit()

    rows_in = loaded = unchanged = 0
    raw_refs: list[str] = []
    release_id: int | None = None
    try:
        # --- Fetch + archive raw + parse ---------------------------------
        parsed: list[tuple[str, ParsedValue]] = []  # (our_geo_code, value)
        for n, target in enumerate(targets, 1):
            for endpoint, parser in ENDPOINTS:
                payload, raw_bytes, url = fetch_json(f"{API_BASE}/{endpoint}", target.params)
                stored = lake.store(
                    f"nso/census2021/{endpoint}/{target.our_code}", raw_bytes, url
                )
                raw_refs.append(stored.payload_path)
                for value in parser(payload, f"{endpoint}[{target.our_code}]"):
                    parsed.append((target.our_code, value))
                    rows_in += 1
            if n % 15 == 0:
                print(f"  fetched {n}/{len(targets)} geographies ...")

        # --- Quality gate BEFORE anything is written ---------------------
        candidates = []
        for _geo_code, pv in parsed:
            iid, unit_id, unit_code = indicator_info[pv.indicator_code]
            candidates.append(
                Candidate(
                    indicator_id=iid,
                    indicator_code=pv.indicator_code,
                    unit_id=unit_id,
                    unit_code=unit_code,
                    period_id=period_id,
                    year=CENSUS_YEAR,
                    value=pv.value,
                )
            )
        result = run_quality_gate(candidates)
        for info in result.infos:
            print(f"  [info] {info}")
        if not result.passed:
            reason = f"{len(result.failures)} quality failure(s): " + "; ".join(
                result.failures[:5]
            )
            cur.execute(
                "UPDATE ingestion_log SET status = 'failed', finished_at = now(),"
                " rows_in = %s, rows_loaded = 0, error_note = %s WHERE id = %s",
                (rows_in, reason[:1000], log_id),
            )
            conn.commit()
            conn.close()
            print("QUALITY GATE BLOCKED THE LOAD — nothing was written:")
            for failure in result.failures[:10]:
                print(f"  - {failure}")
            return 1

        # --- Load under one release, change-aware, batched ---------------
        cur.execute(
            "INSERT INTO releases (dataset_id, release_date) VALUES (%s, CURRENT_DATE)"
            " RETURNING id",
            (dataset_id,),
        )
        release_id = _scalar(cur)
        to_insert: list[tuple[Any, ...]] = []
        for geo_code, pv in parsed:
            iid, unit_id, _ = indicator_info[pv.indicator_code]
            gid = geo_ids[geo_code]
            key = (iid, gid, json.dumps(pv.breakdowns, sort_keys=True, separators=(", ", ": ")))
            existing = latest.get((iid, gid, key[2]))
            if existing is not None and existing == pv.value:
                unchanged += 1
                continue
            to_insert.append(
                (iid, gid, period_id, dataset_id, release_id, pv.value, unit_id,
                 json.dumps(pv.breakdowns))
            )
        for i in range(0, len(to_insert), BATCH):
            cur.executemany(
                "INSERT INTO observations"
                " (indicator_id, geography_id, time_period_id, dataset_id,"
                "  release_id, value, unit_id, breakdowns, status)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'final')",
                to_insert[i : i + BATCH],
            )
        loaded = len(to_insert)

        cur.execute(
            "UPDATE releases SET raw_file_refs = %s WHERE id = %s",
            (json.dumps(raw_refs), release_id),
        )
        cur.execute(
            "UPDATE ingestion_log SET status = 'success', finished_at = now(),"
            " rows_in = %s, rows_loaded = %s, rows_rejected = 0,"
            " raw_file_refs = %s, release_id = %s, error_note = %s WHERE id = %s",
            (rows_in, loaded, json.dumps(raw_refs[:50]), release_id,
             f"unchanged={unchanged}", log_id),
        )
        conn.commit()
    except Exception as exc:  # noqa: BLE001 — any failure must be logged, then surfaced
        conn.rollback()
        cur.execute(
            "UPDATE ingestion_log SET status = 'failed', finished_at = now(),"
            " error_note = %s WHERE id = %s",
            (str(exc)[:1000], log_id),
        )
        conn.commit()
        conn.close()
        print(f"FAILURE: census ingestion failed and was logged. Reason: {exc}")
        return 1

    conn.close()
    print("Census 2021 ingestion summary:")
    print(f"  geographies fetched : {len(targets)} (1 national + 7 provinces + 77 districts)")
    print(f"  values parsed       : {rows_in}")
    print(f"  observations loaded : {loaded}")
    print(f"  unchanged (skipped) : {unchanged}")
    print("  quality gate        : PASSED")
    print(f"  release id          : {release_id}")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
