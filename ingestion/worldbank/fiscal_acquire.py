"""Acquire the World Bank Nepal Fiscal Dashboard sheets (raw-first) — WBF.S1.

THE CHANNEL (proven headless 2026-08-01; recon had expected far worse)
---------------------------------------------------------------------
The dashboard is a Tableau workbook on `dataviz.worldbank.org`. The recon note
said `<view>.csv` returns an HTML shell, and it does — when requested cold. The
missing ingredient is only a session cookie:

    1. GET  /views/NepalFiscalDashboard/<View>?:embed=y   (server sets cookies)
    2. GET  /views/NepalFiscalDashboard/<View>.csv        (same cookie jar)

Step 2 then returns real `text/csv`. No `bootstrapSession`, no session-id
header, no length-prefixed JSON parsing, no browser. Anything more elaborate is
unnecessary here.

WHAT THE PUBLISHER PERMITS
--------------------------
The workbook's own config (`tsConfigContainer`) declares
`allow_export_data: true` and `allow_summary: true`, but
`allow_view_underlying: false`. So the publisher permits the aggregated summary
behind each view and withholds row-level data. This module takes only summary
CSV — the permitted channel — and must not be extended to reach underlying
data.

VIEW STATE IS THE DATA
----------------------
A sheet's CSV contains exactly what its CURRENT view renders, so the default
export is one slice: the federal sheets happen to default to all seven fiscal
years at the top of the hierarchy, while the provincial and local sheets
default to a single year aggregated over places. Tableau's URL filter
parameters drive the view (verified: `Fiscal year`, `Province Name`, `Group2`,
`Type1` all work), which is how WBF.S2 will walk the full grid. Filter values
must match the source's own spelling exactly — `Province Name=Bagmati` returns
data, `Bagmati Province` returns zero rows — so an unmatched value is a loud
failure, never a silent empty.

Run with `make wb-fiscal-acquire`. Options:
    --dry-run     print what would be fetched, fetch nothing
    --limit N     stop after N sheets (testing)
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ingestion.common.io_utf8 import configure_stdout_utf8  # noqa: E402
from ingestion.common.raw_lake import RawLake  # noqa: E402

HOST = "https://dataviz.worldbank.org"
WORKBOOK = "NepalFiscalDashboard"
LANDING_VIEW = "Landingpage"
DATASET_CODE = "worldbank/fiscal-dashboard"
INVENTORY_PATH = Path("reference/wb-fiscal/sheet_inventory.json")
REQUEST_PAUSE_S = 1.0  # be polite: one call per second
# Waits between attempts on a transport error; len + 1 = attempts per request.
RETRY_BACKOFF_S: tuple[float, ...] = (5.0, 15.0)

# A browser-shaped UA. dataviz.worldbank.org sits behind a CDN that serves the
# viz shell rather than data to obviously non-browser clients; identifying the
# project as well would be preferable, and the contact address published on the
# dashboard page (Infonepal@worldbank.org) is recorded in PROVENANCE.md.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# The workbook's own `visible_sheets`, read from the live tsConfigContainer on
# 2026-08-01. `Landing page` is chrome and `lisa_dashboard` is an internal
# scratch sheet; neither carries data, so neither is harvested.
DATA_SHEETS: tuple[str, ...] = (
    "Federal Revenue",
    "Federal Expenditure",
    "Federal Financing",
    "Federal Debt Stock",
    "Federal Fiscal Indicators",
    "Provincial Revenue",
    "Provincial Expenditure",
    "Provincial Financing",
    "Provincial Fiscal Indicators",
    "Provincial Grants",
    "Provincial GDP",
    "Local Level Revenue",
    "Local Level Expenditure",
    "Local Level Financing",
    "Local Level Fiscal Indicators",
    "Local Level Grants",
)

NON_DATA_SHEETS: tuple[str, ...] = ("Landing page", "lisa_dashboard")


class FiscalAcquireError(Exception):
    """The dashboard did not return data — never fall back to a guess."""


@dataclass(frozen=True)
class SheetPayload:
    """One sheet's untouched CSV bytes plus the URL that produced them."""

    sheet: str
    view: str
    source_url: str
    content: bytes

    @property
    def rows(self) -> list[list[str]]:
        text = self.content.decode("utf-8-sig", errors="replace")
        return list(csv.reader(io.StringIO(text)))


def view_name(sheet: str) -> str:
    """Tableau's URL name for a sheet: its name with spaces removed."""
    return sheet.replace(" ", "")


def open_session() -> requests.Session:
    """A session carrying the cookies that make `.csv` return data."""
    session = requests.Session()
    session.headers.update(
        {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
    )
    _get(
        session,
        f"{HOST}/views/{WORKBOOK}/{LANDING_VIEW}",
        {":embed": "y", ":showVizHome": "no"},
        timeout=60,
    )
    return session


def _get(
    session: requests.Session, url: str, params: dict[str, str], timeout: int = 90
) -> requests.Response:
    """GET, surviving a transient network blip but never a real failure.

    A provincial harvest is ~340 requests over six minutes, so one dropped
    connection or slow response is close to certain; without this a single
    timeout throws away the whole run (it did, on 2026-08-04, four minutes in).
    Transport errors only — a response that arrives is handled by the caller,
    which is where a wrong content type is caught. After the last attempt the
    error is re-raised: a source that is genuinely down must still fail loudly.
    """
    for attempt in range(len(RETRY_BACKOFF_S) + 1):
        try:
            return session.get(url, params=params, timeout=timeout)
        except requests.RequestException as exc:
            if attempt == len(RETRY_BACKOFF_S):
                raise
            wait = RETRY_BACKOFF_S[attempt]
            print(
                f"    network error ({type(exc).__name__}); attempt "
                f"{attempt + 1}/{len(RETRY_BACKOFF_S) + 1} failed, "
                f"retrying in {wait:.0f}s"
            )
            time.sleep(wait)
    raise FiscalAcquireError("unreachable: the retry loop always returns or raises")


def fetch_sheet(
    session: requests.Session,
    sheet: str,
    filters: dict[str, str] | None = None,
) -> SheetPayload:
    """Fetch ONE sheet's summary CSV for the given view state.

    Raises FiscalAcquireError rather than returning a shell: a non-CSV response
    means the session lapsed or the view changed, and parsing an HTML shell as
    data is exactly the silent corruption rule 1 exists to prevent.
    """
    view = view_name(sheet)
    params: dict[str, str] = {":embed": "y", **(filters or {})}
    url = f"{HOST}/views/{WORKBOOK}/{view}.csv"

    response = _get(session, url, params)
    content_type = response.headers.get("content-type", "")
    if "csv" not in content_type.lower():
        # One retry: reload the view to refresh the session, then ask again.
        _get(
            session,
            f"{HOST}/views/{WORKBOOK}/{view}",
            {":embed": "y", ":showVizHome": "no"},
            timeout=60,
        )
        time.sleep(REQUEST_PAUSE_S)
        response = _get(session, url, params)
        content_type = response.headers.get("content-type", "")

    if "csv" not in content_type.lower():
        raise FiscalAcquireError(
            f"{sheet}: expected text/csv, got {content_type!r} "
            f"({len(response.content):,} bytes) from {response.url}. "
            "The Tableau session protocol may have changed — re-run the S1 spike "
            "before trusting any parse."
        )
    return SheetPayload(
        sheet=sheet, view=view, source_url=response.url, content=response.content
    )


def describe(payload: SheetPayload) -> dict[str, object]:
    """The inventory record for one sheet: shape and columns, never values."""
    rows = payload.rows
    header = rows[0] if rows else []
    return {
        "sheet": payload.sheet,
        "view": payload.view,
        "source_url": payload.source_url,
        "columns": header,
        "default_view_rows": max(len(rows) - 1, 0),
        "size_bytes": len(payload.content),
    }


def main() -> None:
    configure_stdout_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    sheets = list(DATA_SHEETS[: args.limit] if args.limit else DATA_SHEETS)

    if args.dry_run:
        print(f"Would fetch {len(sheets)} sheet(s) from {HOST}/views/{WORKBOOK}/:")
        for sheet in sheets:
            print(f"  {sheet:32s} -> {view_name(sheet)}.csv")
        return

    session = open_session()
    time.sleep(REQUEST_PAUSE_S)

    payloads: list[SheetPayload] = []
    for sheet in sheets:
        payload = fetch_sheet(session, sheet)
        payloads.append(payload)
        rows = payload.rows
        print(
            f"  {sheet:32s} {max(len(rows) - 1, 0):5d} rows  "
            f"{len(payload.content):,} bytes"
        )
        time.sleep(REQUEST_PAUSE_S)

    # Raw FIRST: archive every untouched payload before anything parses it.
    # One snapshot rather than 16 objects — the free tier hates many small
    # uploads, and store_snapshot keeps each member's bytes and SHA-256 intact.
    lake = RawLake.from_env()
    obj = lake.store_snapshot(
        dataset_code=DATASET_CODE,
        members=[(p.view, p.content, p.source_url) for p in payloads],
        snapshot_filename="sheets.json",
    )
    print(
        f"\nRaw lake: {len(payloads)} sheet(s) archived in {obj.payload_path} "
        f"(sha256 {obj.sha256[:12]}…, {obj.size_bytes:,} bytes)"
    )

    INVENTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    inventory = {
        "workbook": WORKBOOK,
        "host": HOST,
        "harvested_at": obj.fetched_at,
        "raw_lake_payload": obj.payload_path,
        "raw_lake_metadata": obj.metadata_path,
        "non_data_sheets": list(NON_DATA_SHEETS),
        "sheets": [describe(p) for p in payloads],
    }
    INVENTORY_PATH.write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Inventory written to {INVENTORY_PATH}")


if __name__ == "__main__":
    main()
