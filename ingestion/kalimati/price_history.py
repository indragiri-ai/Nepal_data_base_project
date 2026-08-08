"""The market board's OWN average price, 2013 to today (ODN.S2 extension).

WHY THIS EXISTS
---------------
The Open Data Nepal copy of Kalimati stops on 2022-04-18 and carries a daily
LOW and HIGH. The market board publishes its own history directly, and it
reaches today — filling a gap of more than a thousand trading days.

It is a DIFFERENT STATISTIC, and that is the point of loading it separately:

* ODN gives the day's low and high. Its "Average" column is merely the
  midpoint of those two, in every row of the series.
* The market board publishes its own average, which is NOT the midpoint. Its
  own daily page proves it: on 2026-08-07 Tomato Small(Tunnel) shows
  min 30, max 40, average 34.85 — a midpoint would be 35.

So this is the real average, and it is stored under its own indicator rather
than appended to the low/high series. Appending a differently-defined number
to an existing series is how a chart quietly starts lying.

BEING A GOOD GUEST
------------------
The market board's own page carries a policy notice (in Nepali): it detects
heavy request volume from one IP, asks callers to wait between requests, and
warns that ignoring this can get the IP blocked. This module therefore asks
for the WHOLE history of one commodity per request — 24 requests, not 90,000 —
and pauses between them. Do not lower `REQUEST_PAUSE_S`.

NOTHING IS GUESSED
------------------
Commodity codes come from the market's own English option list, matched to our
basket by exact name and recorded in `db/seeds/kalimati_commodity_codes.csv`.
One basket item — "Potato Red" — is not offered by the board any more (it now
lists "Potato Red(Long)" and "Potato Red(Indian)" separately), so it is left
out rather than mapped onto a near-neighbour.

Run with `make kalimati-official` (add `--dry-run` to write nothing).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import psycopg
import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ingestion.common.io_utf8 import configure_stdout_utf8  # noqa: E402
from ingestion.common.raw_lake import RawLake  # noqa: E402
from ingestion.opendatanepal.kalimati_pipeline import seed_indicators  # noqa: E402

HOST = "https://kalimatimarket.gov.np"
FORM_URL = f"{HOST}/price-history"
API_URL = f"{HOST}/api/price-history"
DATASET_CODE = "kalimati/price-history"

CODES_CSV = Path("db/seeds/kalimati_commodity_codes.csv")
SERIES_START = "2013-06-16"  # the first day the ODN copy also has

# The board asks for space between requests, in writing. One request per
# commodity for its entire history keeps the total to two dozen.
#
# Raised from 4s to 12s after the board's server closed the connection on the
# ninth consecutive request ("Remote end closed connection without response").
# That is the policy notice enforcing itself, and the right answer is to ask
# less often — not to retry harder. Do not lower this.
REQUEST_PAUSE_S = 12.0
# Waits before re-trying a dropped connection. Long on purpose: a server that
# just hung up wants quiet, not another request a second later.
RETRY_BACKOFF_S: tuple[float, ...] = (60.0, 180.0)
TIMEOUT_S = 120

# Each commodity's response is cached here as it arrives, so an interrupted run
# resumes instead of asking the board for everything again. Being resumable is
# politeness, not just convenience.
CACHE_DIR = Path(".cache/kalimati-price-history")

SOURCE_NAME = "Kalimati Fruits and Vegetable Market Development Board"
DATASET_NAME = "Kalimati daily price history (market board)"
GEO_CODE = "NP0327101"
UNIT_CODE = "NPR_PER_KG"
INDICATOR = "KALIMATI_PRICE_AVG"

MIN_PRICE = Decimal("0")
MAX_PRICE = Decimal("10000")
BATCH = 5000


class KalimatiOfficialError(Exception):
    """Stop rather than publish something unverified."""


@dataclass(frozen=True)
class AvgRow:
    commodity: str
    day: date
    average: Decimal


def read_codes() -> list[tuple[str, str]]:
    if not CODES_CSV.exists():
        raise KalimatiOfficialError(f"{CODES_CSV} is missing.")
    with CODES_CSV.open(encoding="utf-8", newline="") as fh:
        rows = [(r["commodity"], r["market_code"]) for r in csv.DictReader(fh)]
    if not rows:
        raise KalimatiOfficialError(f"{CODES_CSV} lists no commodities.")
    return rows


def open_session() -> tuple[requests.Session, str]:
    """A session carrying the CSRF token the board's own form sends."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; NepalDataPortal/1.0)",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": FORM_URL,
    })
    page = session.get(FORM_URL, timeout=TIMEOUT_S).text
    match = re.search(r'id="csrf"[^>]*value="([^"]+)"', page) or re.search(
        r'name="_token" value="([^"]+)"', page
    )
    if match is None:
        raise KalimatiOfficialError(
            "no CSRF token on the price-history page — the form changed."
        )
    return session, match.group(1)


def _post_with_backoff(
    session: requests.Session, token: str, code: str, commodity: str, upto: str
) -> tuple[bytes, str, requests.Session, str]:
    """POST once, and on a dropped connection wait a long time and try again.

    A fresh session (and CSRF token) is taken for each retry: when the board
    hangs up, the old connection and possibly the old token are spent.
    """
    url = f"{API_URL}/{code}"
    for attempt in range(len(RETRY_BACKOFF_S) + 1):
        try:
            response = session.post(
                url,
                data={"locale": "en", "_token": token, "from": SERIES_START, "to": upto},
                timeout=TIMEOUT_S,
            )
            if response.status_code != 200:
                raise KalimatiOfficialError(
                    f"{commodity} ({code}): HTTP {response.status_code}"
                )
            return response.content, response.url, session, token
        except requests.RequestException as exc:
            if attempt == len(RETRY_BACKOFF_S):
                raise KalimatiOfficialError(
                    f"{commodity} ({code}): {type(exc).__name__} after "
                    f"{attempt + 1} attempts. The board may be rate-limiting; "
                    "re-run later — finished commodities are cached and will "
                    "not be requested again."
                ) from exc
            wait = RETRY_BACKOFF_S[attempt]
            print(f"      connection dropped; waiting {wait:.0f}s and reopening "
                  "the session")
            time.sleep(wait)
            session, token = open_session()
    raise KalimatiOfficialError("unreachable")  # pragma: no cover


def fetch_commodity(
    session: requests.Session, token: str, code: str, commodity: str, upto: str
) -> tuple[list[AvgRow], bytes, str, requests.Session, str]:
    """The board's whole published history for one commodity."""
    raw, url, session, token = _post_with_backoff(session, token, code, commodity, upto)
    return parse_payload(raw, code, commodity), raw, url, session, token


def parse_payload(raw: bytes, code: str, commodity: str) -> list[AvgRow]:
    """Turn one API response into typed rows, failing loudly on anything odd.

    Separate from fetching so a cached response is read through exactly the
    same checks as a fresh one — including the name check below, which is the
    thing standing between a wrong code and a decade of prices filed under the
    wrong vegetable.
    """
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise KalimatiOfficialError(f"{commodity} ({code}): response was not JSON") from exc

    # The board returns the commodity's own name; if it does not match the one
    # we asked for, the code mapping has drifted and every row would be filed
    # under the wrong vegetable.
    returned = str(payload.get("commodity", "")).strip()
    if returned != commodity:
        raise KalimatiOfficialError(
            f"asked for {commodity!r} (code {code}) but the board returned "
            f"{returned!r} — the code mapping in {CODES_CSV} is wrong."
        )

    prices = payload.get("prices") or {}
    days = prices.get("date") or []
    avgs = prices.get("avg") or []
    if len(days) != len(avgs):
        raise KalimatiOfficialError(
            f"{commodity}: {len(days)} dates but {len(avgs)} averages."
        )

    rows: list[AvgRow] = []
    # strict=True: the length check above already caught a mismatch, and
    # silently truncating to the shorter list would drop real days.
    for raw_day, raw_avg in zip(days, avgs, strict=True):
        try:
            day = date.fromisoformat(str(raw_day).strip()[:10])
        except ValueError as exc:
            raise KalimatiOfficialError(f"{commodity}: unreadable date {raw_day!r}") from exc
        try:
            value = Decimal(str(raw_avg).replace(",", "").strip())
        except (InvalidOperation, ValueError) as exc:
            raise KalimatiOfficialError(
                f"{commodity} on {day}: {raw_avg!r} is not a number"
            ) from exc
        if not (MIN_PRICE < value <= MAX_PRICE):
            raise KalimatiOfficialError(
                f"{commodity} on {day}: {value} is outside (0, {MAX_PRICE}] NPR/kg."
            )
        rows.append(AvgRow(commodity=commodity, day=day, average=value))
    return rows


def harvest(limit: int | None = None) -> tuple[list[AvgRow], list[tuple[str, bytes, str]]]:
    """Every basket commodity's whole history, resuming from cache.

    A commodity already in the cache is NOT re-requested. The board hung up on
    a previous run's ninth consecutive request, and the courteous response is
    to keep what we were already given rather than ask for it twice.
    """
    codes = read_codes()[:limit] if limit else read_codes()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    upto = date.today().isoformat()

    cached = {c for _, c in codes if (CACHE_DIR / f"{c}.json").exists()}
    print(f"{len(codes)} commodities; {len(cached)} already cached, "
          f"{len(codes) - len(cached)} to request "
          f"({REQUEST_PAUSE_S:.0f}s apart — the board's policy):")

    session: requests.Session | None = None
    token = ""
    rows: list[AvgRow] = []
    members: list[tuple[str, bytes, str]] = []

    for i, (commodity, code) in enumerate(codes, start=1):
        path = CACHE_DIR / f"{code}.json"
        if path.exists():
            raw = path.read_bytes()
            got = parse_payload(raw, code, commodity)
            url = f"{API_URL}/{code}"
            source = "cached"
        else:
            if session is None:
                session, token = open_session()
            time.sleep(REQUEST_PAUSE_S)
            got, raw, url, session, token = fetch_commodity(
                session, token, code, commodity, upto
            )
            path.write_bytes(raw)
            source = "fetched"
        rows.extend(got)
        members.append((f"{code}.json", raw, url))
        span = f"{got[0].day} → {got[-1].day}" if got else "no rows"
        print(f"  {i:>2}/{len(codes)}  {commodity:<24} {len(got):>5,} days   "
              f"{span}  ({source})")
    return rows, members


def _scalar(cur: psycopg.Cursor[Any]) -> Any:
    row = cur.fetchone()
    return None if row is None else row[0]


def load(rows: list[AvgRow], dry_run: bool) -> int:
    load_dotenv()
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        raise KalimatiOfficialError("DATABASE_URL is not set")

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM sources WHERE name_en = %s", (SOURCE_NAME,))
        source_id = _scalar(cur)
        if source_id is None:
            raise KalimatiOfficialError(
                f"source {SOURCE_NAME!r} is not seeded — run the ODN loader first."
            )
        cur.execute(
            "INSERT INTO datasets (source_id, name_en, license, update_frequency,"
            "  access_method, documentation_url)"
            " VALUES (%s, %s, %s, 'daily', 'api', %s)"
            " ON CONFLICT (source_id, name_en) DO UPDATE SET"
            "   update_frequency = EXCLUDED.update_frequency,"
            "   documentation_url = EXCLUDED.documentation_url"
            " RETURNING id",
            (
                source_id,
                DATASET_NAME,
                "Nepal government open data; no licence stated on the page — verify",
                FORM_URL,
            ),
        )
        dataset_id = int(_scalar(cur))

        cur.execute("SELECT id FROM units WHERE code = %s", (UNIT_CODE,))
        unit_id = _scalar(cur)
        cur.execute("SELECT id FROM geographies WHERE code = %s", (GEO_CODE,))
        geo_id = _scalar(cur)

        # One definition of these indicators, in one CSV, upserted by whichever
        # loader runs — so the low/high loader and this one cannot drift apart.
        if unit_id is not None:
            print(f"Indicators seeded/updated: "
                  f"{seed_indicators(cur, int(source_id), int(unit_id))}")

        cur.execute("SELECT id FROM indicators WHERE code = %s", (INDICATOR,))
        indicator_id = _scalar(cur)
        if None in (unit_id, geo_id, indicator_id):
            raise KalimatiOfficialError(
                f"unit/geography/indicator not seeded — run `make seed` "
                f"(unit={unit_id}, geo={geo_id}, indicator={indicator_id})."
            )

        # Day periods on demand, as the ODN loader does.
        cur.execute("SELECT gregorian_start, id FROM time_periods WHERE period_type = 'day'")
        periods: dict[date, int] = {d: i for d, i in cur.fetchall()}
        missing = sorted({r.day for r in rows} - set(periods))
        if missing:
            cur.executemany(
                "INSERT INTO time_periods"
                " (period_type, gregorian_start, gregorian_end, gregorian_label, sort_key)"
                " VALUES ('day', %s, %s, %s, %s)"
                " ON CONFLICT (period_type, gregorian_start, gregorian_end) DO NOTHING",
                [(d, d, d.isoformat(), int(d.strftime("%Y%m%d"))) for d in missing],
            )
            cur.execute(
                "SELECT gregorian_start, id FROM time_periods WHERE period_type = 'day'"
            )
            periods = {d: i for d, i in cur.fetchall()}
        print(f"\nDay periods: {len(periods):,} present ({len(missing):,} created)")

        cur.execute(
            "SELECT o.time_period_id, o.breakdowns->>'commodity', o.value"
            " FROM observations o WHERE o.dataset_id = %s AND o.is_latest",
            (dataset_id,),
        )
        latest = {(pid, name): value for pid, name, value in cur.fetchall()}
        print(f"Already loaded (latest): {len(latest):,}")

        to_insert: list[tuple[Any, ...]] = []
        unchanged = 0
        for r in rows:
            pid = periods[r.day]
            if latest.get((pid, r.commodity)) == r.average:
                unchanged += 1
                continue
            to_insert.append(
                (indicator_id, geo_id, pid, dataset_id, r.average, unit_id,
                 json.dumps({"commodity": r.commodity}))
            )

        print(f"To load: {len(to_insert):,}   unchanged (skipped): {unchanged:,}")
        if dry_run:
            print("\nDRY RUN — nothing written.")
            conn.rollback()
            return 0
        if not to_insert:
            print("Nothing to load; the warehouse already matches the board.")
            return 0

        cur.execute(
            "INSERT INTO releases (dataset_id, release_date)"
            " VALUES (%s, CURRENT_DATE) RETURNING id",
            (dataset_id,),
        )
        release_id = _scalar(cur)
        for start in range(0, len(to_insert), BATCH):
            chunk = to_insert[start : start + BATCH]
            cur.executemany(
                "INSERT INTO observations"
                " (indicator_id, geography_id, time_period_id, dataset_id,"
                "  release_id, value, unit_id, breakdowns, status)"
                " VALUES (%s, %s, %s, %s, " + str(release_id) + ", %s, %s, %s, 'final')",
                chunk,
            )
            conn.commit()
            print(f"  committed {min(start + BATCH, len(to_insert)):>7,} / {len(to_insert):,}")
        print(f"Loaded {len(to_insert):,} observations under release {release_id}.")
        return len(to_insert)


def main() -> int:
    configure_stdout_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None, help="first N commodities only")
    parser.add_argument("--no-raw", action="store_true")
    args = parser.parse_args()

    rows, members = harvest(args.limit)
    print(f"\nHarvested {len(rows):,} commodity-days.")
    if not args.no_raw and not args.dry_run:
        stored = RawLake.from_env().store_snapshot(DATASET_CODE, members)
        print(f"Raw -> {stored.payload_path} ({stored.size_bytes:,} bytes)")
    load(rows, args.dry_run)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KalimatiOfficialError as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        sys.exit(2)
