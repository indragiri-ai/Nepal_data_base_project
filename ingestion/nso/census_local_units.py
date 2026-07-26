"""P2B.S8a — load municipality-level (753 local units) census population.

Source: the NSO NPHC 2021 bulk table `Census_data/Indv01_PopulationBySex.csv`
(downloaded), which carries population/male/female for every local unit with its
own (prov, dist, gapa) codes. We map each unit to our geography via the official
`adm3_pcode` crosswalk (reference/census/local_unit_crosswalk.csv, verified
against OCHA COD-AB) and load `CENSUS_POP_TOTAL` (total + male/female breakdowns)
at level=local_unit.

Raw-first: the source CSV is archived to the raw lake before anything is written.
Idempotent: re-running writes only genuinely changed values (is_latest trigger
demotes old rows). Nothing is guessed — a local unit whose codes are not in the
crosswalk fails the run with a report.

    make ingest-census-local
"""

from __future__ import annotations

import csv
import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv

from ingestion.common.io_utf8 import configure_stdout_utf8
from ingestion.common.quality import Candidate, run_quality_gate
from ingestion.common.raw_lake import RawLake

DATASET_NAME = "National Population and Housing Census 2021"
CENSUS_YEAR = 2021
SOURCE_CSV = Path("Census_data/Indv01_PopulationBySex.csv")
CROSSWALK_CSV = Path("reference/census/local_unit_crosswalk.csv")
BATCH = 1000


def _scalar(cur: psycopg.Cursor[Any]) -> Any:
    row = cur.fetchone()
    return None if row is None else row[0]


def load_crosswalk() -> dict[tuple[str, str], str]:
    """(census_dist, census_gapa) -> official adm3_pcode."""
    out: dict[tuple[str, str], str] = {}
    with CROSSWALK_CSV.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[(r["census_dist"], r["census_gapa"])] = r["adm3_pcode"]
    return out


def parse_source(
    crosswalk: dict[tuple[str, str], str],
) -> tuple[list[tuple[str, dict[str, str], Decimal]], list[str]]:
    """Return [(adm3_pcode, breakdowns, value) for CENSUS_POP_TOTAL] and failures.

    Skips the national/province/district/INSTITUTIONAL rows — only the 753 named
    local units. total -> {}; male -> {'sex':'male'}; female -> {'sex':'female'}.
    """
    values: list[tuple[str, dict[str, str], Decimal]] = []
    failures: list[str] = []
    seen: set[str] = set()
    with SOURCE_CSV.open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if r["prov"] == "0" or r["dist"] == "0" or r["gapa"] in ("0", "99"):
                continue
            pcode = crosswalk.get((r["dist"], r["gapa"]))
            if pcode is None:
                failures.append(
                    f"census dist={r['dist']} gapa={r['gapa']} ({r['gapaname']}): not in crosswalk"
                )
                continue
            seen.add(pcode)
            values.append((pcode, {}, Decimal(r["total"])))
            values.append((pcode, {"sex": "male"}, Decimal(r["male"])))
            values.append((pcode, {"sex": "female"}, Decimal(r["female"])))
    if len(seen) != 753:
        failures.append(f"expected 753 local units, mapped {len(seen)}")
    return values, failures


def run() -> int:
    configure_stdout_utf8()
    load_dotenv()
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        print("FAILURE: DATABASE_URL is empty. Fill in .env.")
        return 1
    if not SOURCE_CSV.exists():
        print(f"FAILURE: {SOURCE_CSV} not found (the NSO census download).")
        return 1

    crosswalk = load_crosswalk()
    values, failures = parse_source(crosswalk)
    if failures:
        print("FAILURE: source did not reconcile (reported, not guessed):")
        for f in failures[:10]:
            print(f"  - {f}")
        return 1
    total_pop = sum(v for pc, b, v in values if b == {})
    print(f"Parsed {len(values)} values for {len({pc for pc, _, _ in values})} local units;"
          f" municipality population sum = {total_pop:,} (expected 28,925,480)")

    lake = RawLake.from_env()
    conn = psycopg.connect(db_url, connect_timeout=30)
    cur = conn.cursor()

    cur.execute("SELECT id FROM datasets WHERE name_en = %s", (DATASET_NAME,))
    dataset_id = _scalar(cur)
    cur.execute(
        "SELECT id FROM time_periods WHERE period_type = 'year' AND gregorian_label = %s",
        (str(CENSUS_YEAR),),
    )
    period_id = _scalar(cur)
    cur.execute(
        "SELECT id, unit_id FROM indicators WHERE code = 'CENSUS_POP_TOTAL'"
    )
    ind_row = cur.fetchone()
    cur.execute(
        "SELECT u.code FROM indicators i JOIN units u ON u.id = i.unit_id"
        " WHERE i.code = 'CENSUS_POP_TOTAL'"
    )
    unit_code = _scalar(cur)
    cur.execute("SELECT code, id FROM geographies WHERE level = 'local_unit'")
    geo_ids: dict[str, int] = dict(cur.fetchall())

    if dataset_id is None or period_id is None or ind_row is None or not geo_ids:
        print("FAILURE: reference data missing — run `make seed` and `make seed-census` first.")
        conn.close()
        return 1
    indicator_id, unit_id = ind_row
    missing = [pc for pc, _, _ in values if pc not in geo_ids]
    if missing:
        print(
            f"FAILURE: {len(missing)} local-unit geographies not seeded"
            f" (e.g. {missing[:3]}) — run `make seed`."
        )
        conn.close()
        return 1

    # --- Raw-first: archive the source table before writing anything --------
    stored = lake.store("nso/census2021/local_units/Indv01_PopulationBySex",
                        SOURCE_CSV.read_bytes(), f"file://{SOURCE_CSV}", content_type="text/csv",
                        payload_filename="Indv01_PopulationBySex.csv")
    raw_refs = [stored.payload_path]

    # --- Quality gate BEFORE any write --------------------------------------
    candidates = [
        Candidate(indicator_id=indicator_id, indicator_code="CENSUS_POP_TOTAL",
                  unit_id=unit_id, unit_code=unit_code, period_id=period_id,
                  year=CENSUS_YEAR, value=v)
        for _pc, _b, v in values
    ]
    result = run_quality_gate(candidates)
    if not result.passed:
        cur.execute(
            "INSERT INTO ingestion_log"
            " (dataset_id, status, finished_at, rows_in, rows_loaded, error_note)"
            " VALUES (%s, 'failed', now(), %s, 0, %s)",
            (dataset_id, len(values), ("; ".join(result.failures[:5]))[:1000]),
        )
        conn.commit()
        conn.close()
        print("QUALITY GATE BLOCKED THE LOAD — nothing written:")
        for f in result.failures[:10]:
            print(f"  - {f}")
        return 1

    cur.execute(
        "INSERT INTO ingestion_log (dataset_id, status) VALUES (%s, 'running') RETURNING id",
        (dataset_id,),
    )
    log_id = _scalar(cur)
    # current latest values so re-runs only write changes
    cur.execute(
        "SELECT geography_id, breakdowns::text, value FROM observations"
        " WHERE is_latest AND time_period_id = %s AND indicator_id = %s",
        (period_id, indicator_id),
    )
    latest = {(g, b): v for g, b, v in cur.fetchall()}
    conn.commit()

    loaded = unchanged = 0
    release_id: int | None = None
    try:
        cur.execute(
            "INSERT INTO releases (dataset_id, release_date)"
            " VALUES (%s, CURRENT_DATE) RETURNING id",
            (dataset_id,),
        )
        release_id = _scalar(cur)
        to_insert: list[tuple[Any, ...]] = []
        for pcode, breakdowns, value in values:
            gid = geo_ids[pcode]
            bkey = json.dumps(breakdowns, sort_keys=True, separators=(", ", ": "))
            if latest.get((gid, bkey)) == value:
                unchanged += 1
                continue
            to_insert.append((indicator_id, gid, period_id, dataset_id, release_id,
                              value, unit_id, json.dumps(breakdowns)))
        for i in range(0, len(to_insert), BATCH):
            cur.executemany(
                "INSERT INTO observations"
                " (indicator_id, geography_id, time_period_id, dataset_id,"
                "  release_id, value, unit_id, breakdowns, status)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'final')",
                to_insert[i : i + BATCH],
            )
        loaded = len(to_insert)
        cur.execute("UPDATE releases SET raw_file_refs = %s WHERE id = %s",
                    (json.dumps(raw_refs), release_id))
        cur.execute(
            "UPDATE ingestion_log SET status='success', finished_at=now(), rows_in=%s,"
            " rows_loaded=%s, rows_rejected=0, raw_file_refs=%s, release_id=%s,"
            " error_note=%s WHERE id=%s",
            (len(values), loaded, json.dumps(raw_refs), release_id,
             f"unchanged={unchanged}", log_id),
        )
        conn.commit()
    except Exception as exc:  # noqa: BLE001 — log then surface
        conn.rollback()
        cur.execute(
            "UPDATE ingestion_log SET status='failed', finished_at=now(),"
            " error_note=%s WHERE id=%s",
            (str(exc)[:1000], log_id),
        )
        conn.commit()
        conn.close()
        print(f"FAILURE: local-unit census ingestion failed and was logged. Reason: {exc}")
        return 1

    conn.close()
    print("Municipality census (CENSUS_POP_TOTAL) ingestion summary:")
    print("  local units         : 753")
    print(f"  values parsed       : {len(values)} (total + male + female)")
    print(f"  observations loaded : {loaded}")
    print(f"  unchanged (skipped) : {unchanged}")
    print("  quality gate        : PASSED")
    print(f"  release id          : {release_id}")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
