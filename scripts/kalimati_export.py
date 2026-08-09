"""Publish the WHOLE Kalimati price dataset as downloadable CSV files.

WHY THIS EXISTS
---------------
The warehouse holds a curated 25-commodity basket because rows cost database
space on a 500 MB free tier. The RAW LAKE holds all of it — every commodity,
every trading day, exactly as published. Downloading does not need a database,
so there is no reason for the download to be limited to what is charted.

This turns the archive into files anyone can take away:

    kalimati-daily-prices.csv   every commodity, every day, as published
    README.txt                  what the columns mean and what to distrust

The market board's own website offers no export of any kind — no CSV, no
download button, on either its daily price page or its history chart. So this
is the part of the portal that most clearly earns its place: the same public
data, in a form you can actually work with.

WHAT IS INCLUDED, DELIBERATELY
------------------------------
* **All 131 commodities**, not the charted 25.
* **All units**, not just Kg. Rows priced per piece or per dozen are excluded
  from the warehouse because they cannot be compared with per-kg figures, but
  they are real published prices and the `unit` column says which is which.
  Leaving them out of a bulk export would be editing the archive.
* The market board's **own average** where we have it, in its own column, kept
  separate from the low/high pair because it is a different statistic.

Run with `make kalimati-export`.
"""

from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingestion.common.io_utf8 import configure_stdout_utf8  # noqa: E402
from ingestion.opendatanepal.kalimati_acquire import (  # noqa: E402
    BROKEN_FIELDS,
    BROKEN_RESOURCE,
    CLEAN_FIELDS,
    CLEAN_RESOURCE,
    parse_rows,
)

DOWNLOAD_BUCKET = "downloads"
PREFIX = "kalimati"
PRICES_FILE = "kalimati-daily-prices.csv"
README_FILE = "README.txt"


class ExportError(Exception):
    """Refuse to publish something we cannot vouch for."""


def _storage(url: str, key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}", "apikey": key}


def ensure_public_bucket(url: str, key: str) -> None:
    """A PUBLIC bucket, separate from the private raw lake.

    The raw lake stays private: it is the immutable evidence trail, not a
    product. Published downloads are a different thing with a different
    audience, so they get their own bucket rather than opening up the archive.
    """
    headers = _storage(url, key)
    existing = requests.get(f"{url}/storage/v1/bucket", headers=headers, timeout=30)
    names = {b["name"]: b for b in existing.json()} if existing.ok else {}
    if DOWNLOAD_BUCKET in names:
        if not names[DOWNLOAD_BUCKET].get("public"):
            raise ExportError(
                f"bucket {DOWNLOAD_BUCKET!r} exists but is private; downloads "
                "would 404 for the public. Make it public in the dashboard."
            )
        print(f"bucket {DOWNLOAD_BUCKET!r}: already present and public")
        return
    resp = requests.post(
        f"{url}/storage/v1/bucket",
        headers={**headers, "Content-Type": "application/json"},
        json={"name": DOWNLOAD_BUCKET, "id": DOWNLOAD_BUCKET, "public": True},
        timeout=30,
    )
    if not resp.ok:
        raise ExportError(f"could not create bucket ({resp.status_code}): {resp.text}")
    print(f"bucket {DOWNLOAD_BUCKET!r}: created (public)")


def newest_snapshot(url: str, key: str, bucket: str, prefix: str) -> str:
    """The most recent raw-lake snapshot under a prefix."""
    resp = requests.post(
        f"{url}/storage/v1/object/list/{bucket}",
        headers={**_storage(url, key), "Content-Type": "application/json"},
        json={"prefix": prefix, "limit": 100, "sortBy": {"column": "name", "order": "desc"}},
        timeout=60,
    )
    names = [o["name"] for o in resp.json() if o.get("name")]
    if not names:
        raise ExportError(f"no raw-lake objects under {prefix!r}")
    return f"{prefix}/{sorted(names)[-1]}/snapshot.json"


def read_snapshot_rows(
    url: str, key: str, bucket: str, path: str, fields: tuple[str, ...]
) -> list[Any]:
    """Parse every page of an archived snapshot back into typed rows."""
    resp = requests.get(
        f"{url}/storage/v1/object/{bucket}/{path}", headers=_storage(url, key), timeout=300
    )
    if not resp.ok:
        raise ExportError(f"could not read {path} ({resp.status_code})")
    snapshot = json.loads(resp.content)
    rows: list[Any] = []
    for member_key, member in snapshot["members"].items():
        if not member_key.startswith("page_"):
            continue  # package_show metadata, not data
        payload = json.loads(base64.b64decode(member["payload_b64"]))
        rows.extend(parse_rows(payload["result"]["records"], fields))
    return rows


def board_averages(dsn: str) -> dict[tuple[str, date], Any]:
    with psycopg.connect(dsn, connect_timeout=30) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT o.breakdowns->>'commodity', t.gregorian_start, o.value"
            " FROM observations o"
            " JOIN indicators i ON i.id = o.indicator_id"
            " JOIN time_periods t ON t.id = o.time_period_id"
            " WHERE i.code = 'KALIMATI_PRICE_AVG' AND o.is_latest"
        )
        return {(c, d): v for c, d, v in cur.fetchall()}


def build_csv(rows: list[Any], averages: dict[tuple[str, date], Any]) -> tuple[bytes, int]:
    buf = io.StringIO(newline="")
    writer = csv.writer(buf)
    writer.writerow([
        "commodity", "date", "unit",
        "low_npr", "high_npr", "market_board_average_npr",
    ])
    seen: set[tuple[str, date]] = set()
    written = 0
    for r in sorted(rows, key=lambda x: (x.commodity, x.day)):
        key = (r.commodity, r.day)
        if key in seen:
            continue  # the two source files overlap by four months
        seen.add(key)
        avg = averages.get(key)
        writer.writerow([
            r.commodity, r.day.isoformat(), r.unit,
            r.minimum, r.maximum, "" if avg is None else avg,
        ])
        written += 1

    # Board-average days AFTER the low/high series ends belong in the file too;
    # dropping them would hide four years of prices from anyone downloading.
    for (commodity, day), avg in sorted(averages.items()):
        if (commodity, day) in seen:
            continue
        writer.writerow([commodity, day.isoformat(), "Kg", "", "", avg])
        written += 1

    return buf.getvalue().encode("utf-8"), written


def build_readme(rows: int, commodities: int, first: date, last: date) -> bytes:
    return f"""KALIMATI DAILY WHOLESALE PRICES
================================

{rows:,} rows covering {commodities} commodities, {first} to {last}.
Prices are in Nepali rupees at the Kalimati Fruits and Vegetable Market,
Kathmandu — Nepal's largest wholesale produce market.

COLUMNS
-------
commodity                 as the market publishes it, spelling unchanged
date                      trading day (YYYY-MM-DD)
unit                      Kg, Doz, 1 Pc — CHECK THIS before comparing prices
low_npr                   the day's lowest price
high_npr                  the day's highest price
market_board_average_npr  the board's OWN published average

READ THIS BEFORE USING THE NUMBERS
----------------------------------
1. The average is NOT the midpoint of low and high. Where both appear they
   differ on about 46% of days. Do not compute one from the other.

2. low/high come from the Kalimati dataset re-published by Open Data Nepal,
   which ENDS 2022-04-18. The board's average comes from the board directly
   and continues past that date. Rows after April 2022 therefore have an
   average but no low/high — that is the sources, not missing data.

3. Units are mixed. Rows priced per dozen or per piece cannot be compared with
   per-kilogram rows. They are included because they are real published prices;
   filter on `unit` before any analysis.

4. Some board averages read exactly 999.99. For 16 days of Lime in 2018 the
   board reports 999.99 while its own low and high those days were 1,000-1,500.
   An average cannot sit below the minimum, so those are a field-width limit,
   not prices. They are left as published rather than silently altered.

SOURCE AND CREDIT
-----------------
Kalimati Fruits and Vegetable Market Development Board (kalimatimarket.gov.np),
which records and publishes these prices. The low/high series is redistributed
by Open Data Nepal under CC BY 4.0.

Published by the Nepal Data Portal. Every figure here traces back to an
archived, hash-verified copy of the original response.
Generated {date.today().isoformat()}.
""".encode()


def upload(url: str, key: str, path: str, data: bytes, content_type: str) -> str:
    headers = {**_storage(url, key), "Content-Type": content_type, "x-upsert": "true"}
    resp = requests.post(
        f"{url}/storage/v1/object/{DOWNLOAD_BUCKET}/{path}",
        data=data, headers=headers, timeout=300,
    )
    if not resp.ok:
        raise ExportError(f"upload of {path} failed ({resp.status_code}): {resp.text}")
    return f"{url}/storage/v1/object/public/{DOWNLOAD_BUCKET}/{path}"


def main() -> int:
    configure_stdout_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="build, upload nothing")
    args = parser.parse_args()

    load_dotenv()
    url = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_KEY"]
    lake = os.environ["STORAGE_BUCKET"]
    dsn = os.environ["DATABASE_URL"]

    print("Reading the archive (all commodities, not just the charted basket)…")
    rows: list[Any] = []
    for resource, fields in ((CLEAN_RESOURCE, CLEAN_FIELDS), (BROKEN_RESOURCE, BROKEN_FIELDS)):
        path = newest_snapshot(
            url, key, lake, f"opendatanepal/kalimati-tarkari-dataset/{resource}"
        )
        got = read_snapshot_rows(url, key, lake, path, fields)
        print(f"  {resource[:8]}…  {len(got):>7,} rows   from {path.split('/')[-2]}")
        rows.extend(got)

    print("Reading the market board's own averages from the warehouse…")
    averages = board_averages(dsn)
    print(f"  {len(averages):,} commodity-days")

    payload, written = build_csv(rows, averages)
    commodities = len({r.commodity for r in rows} | {c for c, _ in averages})
    days = [r.day for r in rows] + [d for _, d in averages]
    readme = build_readme(written, commodities, min(days), max(days))

    print(f"\n{PRICES_FILE}: {written:,} rows, {len(payload) / 1_000_000:.1f} MB")
    print(f"{README_FILE}: {len(readme):,} bytes")

    if args.dry_run:
        Path("kalimati-daily-prices.sample.csv").write_bytes(
            b"\n".join(payload.split(b"\n")[:6])
        )
        print("\nDRY RUN — nothing uploaded; wrote a 5-row sample locally.")
        return 0

    ensure_public_bucket(url, key)
    for name, data, ctype in (
        (PRICES_FILE, payload, "text/csv"),
        (README_FILE, readme, "text/plain"),
    ):
        link = upload(url, key, f"{PREFIX}/{name}", data, ctype)
        print(f"  published: {link}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ExportError as exc:
        print(f"\nEXPORT FAILED: {exc}", file=sys.stderr)
        sys.exit(2)
