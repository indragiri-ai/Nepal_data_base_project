"""Load Census 2021 household drinking-water sources at every geography level.

Source: ``Census_data/Hhld06_SourceOfDrinkingWater.csv`` from the NSO NPHC 2021
bulk download. The source category codes are preserved verbatim in
``breakdowns["category"]`` because ``a_TapPiped1`` and ``b_TapPiped2`` are not
self-explanatory and this project never guesses source labels.

The untouched CSV is archived before parsing. Rows are mapped only through the
curated NSO geography references, quality-gated before database writes, and
inserted in batches only when the full observation cell has changed.

    make ingest-census-drinking-water
"""

from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv

from ingestion.common.io_utf8 import configure_stdout_utf8
from ingestion.common.quality import Candidate, run_quality_gate
from ingestion.common.raw_lake import RawLake

DATASET_NAME = "National Population and Housing Census 2021"
INDICATOR_CODE = "CENSUS_HH_DRINKING_WATER"
CENSUS_YEAR = 2021
SOURCE_CSV = Path("Census_data/Hhld06_SourceOfDrinkingWater.csv")
GEO_IDS_CSV = Path("reference/census/nso_geo_ids.csv")
CROSSWALK_CSV = Path("reference/census/local_unit_crosswalk.csv")
BATCH = 1000
EXPECTED_LEVEL_COUNTS = {
    "country": 1,
    "province": 7,
    "district": 77,
    "local_unit": 753,
}
EXPECTED_NATIONAL_TOTAL = Decimal("6660841")
CATEGORY_COLUMNS = (
    "a_TapPiped1",
    "b_TapPiped2",
    "c_Tubewell",
    "d_CoveredWell",
    "e_UncoverWell",
    "f_Spoutwater",
    "g_RiverStream",
    "h_JarBottle",
    "i_Others",
)
SOURCE_COLUMNS = (
    "prov",
    "dist",
    "gapa",
    "provname",
    "dname",
    "gapaname",
    "rowtotal",
    *CATEGORY_COLUMNS,
)


@dataclass(frozen=True)
class GeographyMaps:
    provinces: dict[str, str]
    districts: dict[str, str]
    local_units: dict[tuple[str, str], str]


@dataclass(frozen=True)
class ParsedValue:
    geography_code: str
    breakdowns: dict[str, str]
    value: Decimal


def _scalar(cur: psycopg.Cursor[Any]) -> Any:
    row = cur.fetchone()
    return None if row is None else row[0]


def load_geography_maps() -> GeographyMaps:
    """Load only the curated numeric-code-to-P-code mappings."""
    provinces: dict[str, str] = {}
    districts: dict[str, str] = {}
    with GEO_IDS_CSV.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row["level"] == "province":
                provinces[row["nso_province"]] = row["our_code"]
            elif row["level"] == "district":
                districts[row["nso_district"]] = row["our_code"]

    local_units: dict[tuple[str, str], str] = {}
    with CROSSWALK_CSV.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            local_units[(row["census_dist"], row["census_gapa"])] = row["adm3_pcode"]
    return GeographyMaps(provinces, districts, local_units)


def _map_geography(
    row: dict[str, str], maps: GeographyMaps
) -> tuple[str, str] | None:
    """Return ``(P-code, level)``; institutional rows return ``None``."""
    prov, dist, gapa = row["prov"], row["dist"], row["gapa"]
    if prov == "0":
        return "NP", "country"
    if dist == "0":
        code = maps.provinces.get(prov)
        return (code, "province") if code is not None else None
    if gapa == "0":
        code = maps.districts.get(dist)
        return (code, "district") if code is not None else None
    if gapa == "99":
        return None
    code = maps.local_units.get((dist, gapa))
    return (code, "local_unit") if code is not None else None


def parse_source(
    source_csv: Path, maps: GeographyMaps
) -> tuple[list[ParsedValue], list[str], Counter[str], int]:
    """Parse headline and category values, returning failures rather than guessing."""
    values: list[ParsedValue] = []
    failures: list[str] = []
    level_counts: Counter[str] = Counter()
    institutional_rows = 0
    seen: set[str] = set()

    with source_csv.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if tuple(reader.fieldnames or ()) != SOURCE_COLUMNS:
            return (
                [],
                [
                    "unexpected columns: expected "
                    f"{list(SOURCE_COLUMNS)}, got {reader.fieldnames or []}"
                ],
                level_counts,
                institutional_rows,
            )

        for line_number, row in enumerate(reader, 2):
            if row["gapa"] == "99":
                institutional_rows += 1
                continue

            mapped = _map_geography(row, maps)
            if mapped is None:
                failures.append(
                    f"line {line_number}: unmapped prov={row['prov']} dist={row['dist']} "
                    f"gapa={row['gapa']} ({row['gapaname']})"
                )
                continue
            geography_code, level = mapped
            if geography_code in seen:
                failures.append(
                    f"line {line_number}: duplicate geography {geography_code} "
                    f"({row['gapaname']})"
                )
                continue

            try:
                total = Decimal(row["rowtotal"])
                categories = {column: Decimal(row[column]) for column in CATEGORY_COLUMNS}
            except (InvalidOperation, KeyError) as exc:
                failures.append(f"line {line_number}: invalid numeric value ({exc})")
                continue
            if total < 0 or any(value < 0 for value in categories.values()):
                failures.append(f"line {line_number}: household counts cannot be negative")
                continue
            if sum(categories.values()) != total:
                failures.append(
                    f"line {line_number}: categories sum to {sum(categories.values())}, "
                    f"not rowtotal {total}"
                )
                continue

            seen.add(geography_code)
            level_counts[level] += 1
            values.append(ParsedValue(geography_code, {}, total))
            values.extend(
                ParsedValue(geography_code, {"category": column}, value)
                for column, value in categories.items()
            )

    return values, failures, level_counts, institutional_rows


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

    # Raw-first: archive the untouched source before parsing it.
    lake = RawLake.from_env()
    stored = lake.store(
        "nso/census2021/households/Hhld06_SourceOfDrinkingWater",
        SOURCE_CSV.read_bytes(),
        f"file://{SOURCE_CSV}",
        content_type="text/csv",
        payload_filename=SOURCE_CSV.name,
    )
    raw_refs = [stored.payload_path]

    maps = load_geography_maps()
    values, failures, level_counts, institutional_rows = parse_source(SOURCE_CSV, maps)
    if level_counts != Counter(EXPECTED_LEVEL_COUNTS):
        failures.append(
            f"expected geography counts {EXPECTED_LEVEL_COUNTS}, got {dict(level_counts)}"
        )
    national = next(
        (value.value for value in values if value.geography_code == "NP" and not value.breakdowns),
        None,
    )
    if national != EXPECTED_NATIONAL_TOTAL:
        failures.append(
            f"national rowtotal expected {EXPECTED_NATIONAL_TOTAL}, got {national}"
        )
    for level in ("province", "district", "local_unit"):
        subtotal = sum(
            value.value
            for value in values
            if not value.breakdowns
            and (
                (level == "province" and len(value.geography_code) == 4)
                or (level == "district" and len(value.geography_code) == 6)
                or (level == "local_unit" and len(value.geography_code) == 9)
            )
        )
        if subtotal != EXPECTED_NATIONAL_TOTAL:
            failures.append(
                f"{level} headline rows sum to {subtotal}, expected {EXPECTED_NATIONAL_TOTAL}"
            )
    if failures:
        print("FAILURE: source did not reconcile (reported, not guessed):")
        for failure in failures[:10]:
            print(f"  - {failure}")
        return 1

    print(
        f"Parsed {len(values):,} values for {sum(level_counts.values())} geographies; "
        f"national households = {national:,}"
    )

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
        "SELECT i.id, i.unit_id, u.code FROM indicators i "
        "JOIN units u ON u.id = i.unit_id WHERE i.code = %s",
        (INDICATOR_CODE,),
    )
    indicator_row = cur.fetchone()
    cur.execute("SELECT code, id FROM geographies")
    geo_ids: dict[str, int] = dict(cur.fetchall())

    if dataset_id is None or period_id is None or indicator_row is None:
        print("FAILURE: reference data missing — run `make seed` and `make seed-census` first.")
        conn.close()
        return 1
    indicator_id, unit_id, unit_code = indicator_row
    missing = sorted({value.geography_code for value in values} - geo_ids.keys())
    if missing:
        print(f"FAILURE: {len(missing)} geographies not seeded (e.g. {missing[:3]}).")
        conn.close()
        return 1

    # Quality gate before any observation/release write.
    candidates = [
        Candidate(
            indicator_id=indicator_id,
            indicator_code=INDICATOR_CODE,
            unit_id=unit_id,
            unit_code=unit_code,
            period_id=period_id,
            year=CENSUS_YEAR,
            value=value.value,
        )
        for value in values
    ]
    result = run_quality_gate(candidates)
    if not result.passed:
        cur.execute(
            "INSERT INTO ingestion_log "
            "(dataset_id, status, finished_at, rows_in, rows_loaded, error_note) "
            "VALUES (%s, 'failed', now(), %s, 0, %s)",
            (dataset_id, len(values), ("; ".join(result.failures[:5]))[:1000]),
        )
        conn.commit()
        conn.close()
        print("QUALITY GATE BLOCKED THE LOAD — nothing written:")
        for failure in result.failures[:10]:
            print(f"  - {failure}")
        return 1

    cur.execute(
        "INSERT INTO ingestion_log (dataset_id, status) VALUES (%s, 'running') RETURNING id",
        (dataset_id,),
    )
    log_id = _scalar(cur)
    cur.execute(
        "SELECT geography_id, breakdowns::text, value FROM observations "
        "WHERE is_latest AND time_period_id = %s AND indicator_id = %s",
        (period_id, indicator_id),
    )
    latest = {
        (geography_id, breakdowns): value
        for geography_id, breakdowns, value in cur.fetchall()
    }
    conn.commit()

    loaded = unchanged = 0
    release_id: int | None = None
    try:
        cur.execute(
            "INSERT INTO releases (dataset_id, release_date) "
            "VALUES (%s, CURRENT_DATE) RETURNING id",
            (dataset_id,),
        )
        release_id = _scalar(cur)
        to_insert: list[tuple[Any, ...]] = []
        for value in values:
            geography_id = geo_ids[value.geography_code]
            breakdown_key = json.dumps(
                value.breakdowns, sort_keys=True, separators=(", ", ": ")
            )
            if latest.get((geography_id, breakdown_key)) == value.value:
                unchanged += 1
                continue
            to_insert.append(
                (
                    indicator_id,
                    geography_id,
                    period_id,
                    dataset_id,
                    release_id,
                    value.value,
                    unit_id,
                    json.dumps(value.breakdowns),
                )
            )
        for offset in range(0, len(to_insert), BATCH):
            cur.executemany(
                "INSERT INTO observations "
                "(indicator_id, geography_id, time_period_id, dataset_id, "
                "release_id, value, unit_id, breakdowns, status) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'final')",
                to_insert[offset : offset + BATCH],
            )
        loaded = len(to_insert)
        cur.execute(
            "UPDATE releases SET raw_file_refs = %s WHERE id = %s",
            (json.dumps(raw_refs), release_id),
        )
        cur.execute(
            "UPDATE ingestion_log SET status='success', finished_at=now(), rows_in=%s, "
            "rows_loaded=%s, rows_rejected=0, raw_file_refs=%s, release_id=%s, "
            "error_note=%s WHERE id=%s",
            (
                len(values),
                loaded,
                json.dumps(raw_refs),
                release_id,
                f"unchanged={unchanged}; institutional_rows_skipped={institutional_rows}",
                log_id,
            ),
        )
        conn.commit()
    except Exception as exc:  # noqa: BLE001 — log then surface
        conn.rollback()
        cur.execute(
            "UPDATE ingestion_log SET status='failed', finished_at=now(), "
            "error_note=%s WHERE id=%s",
            (str(exc)[:1000], log_id),
        )
        conn.commit()
        conn.close()
        print(f"FAILURE: drinking-water census ingestion failed and was logged. Reason: {exc}")
        return 1

    conn.close()
    print("Household drinking-water census ingestion summary:")
    print(f"  geographies         : {sum(level_counts.values())} {dict(level_counts)}")
    print(f"  values parsed       : {len(values):,} (headline + 9 source-code breakdowns)")
    print(f"  institutional rows  : {institutional_rows} (skipped)")
    print(f"  observations loaded : {loaded:,}")
    print(f"  unchanged (skipped) : {unchanged:,}")
    print("  quality gate        : PASSED")
    print(f"  release id          : {release_id}")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
