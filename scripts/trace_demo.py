"""Traceability drill (P1.S12): trace one chart number back to its raw source.

Throwaway demo script for the Phase 1 exit checklist. Traces Nepal GDP growth
2020 — the COVID dip visible on the chart — through every layer down to the
raw-lake object and the live source URL.
"""

from __future__ import annotations

import json
import os
import time

import psycopg
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), os.pardir, ".env"))

start = time.perf_counter()
with psycopg.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
    cur.execute(
        """
        SELECT o.id, o.value, o.status, o.is_latest,
               t.gregorian_label, r.id, r.release_date, r.raw_file_refs,
               s.name_en, d.name_en, d.documentation_url, i.source_concept
        FROM observations o
        JOIN indicators i ON i.id = o.indicator_id
        JOIN time_periods t ON t.id = o.time_period_id
        JOIN releases r ON r.id = o.release_id
        JOIN datasets d ON d.id = o.dataset_id
        JOIN sources s ON s.id = d.source_id
        WHERE i.code = 'GDP_GROWTH' AND t.gregorian_label = '2020' AND o.is_latest
        """
    )
    row = cur.fetchone()

assert row is not None, "no is_latest GDP_GROWTH 2020 row found"
oid, val, status, latest, year, rid, rdate, refs, src, ds, doc, wdi_code = row
refs = refs if isinstance(refs, list) else json.loads(refs)
# Raw-lake paths are keyed by the WDI source code (e.g. NY.GDP.MKTP.KD.ZG).
sample = next((x for x in refs if wdi_code in json.dumps(x)), refs[0])

print(f"1. CHART value (what you see)    : GDP growth {year} = {float(val):.2f}%")
print(f"2. observations row id           : {oid}  (status={status}, is_latest={latest})")
print(f"3. produced by release id        : {rid}  (release_date={rdate})")
print(f"4. dataset / source              : {src} - {ds}  (WDI code {wdi_code})")
print(f"5. raw-lake object for {wdi_code}:")
print(f"     {json.dumps(sample)[:260]}")
print(f"6. live source URL               : {doc}")
print()
print(f"Trace completed in {time.perf_counter() - start:.2f} seconds.")
