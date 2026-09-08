"""Reading the BIPAD portal — Nepal's national disaster information system.

BIPAD is run by NDRRMA (the National Disaster Risk Reduction and Management
Authority) and is the origin, not an aggregator: the incidents in it are the
government's own records, fed by police and local-government reporting. So the
`sources` row is NDRRMA, and `datasets` names the BIPAD portal.

WHAT WAS VERIFIED LIVE, 2026-09-07 (cite these; do not re-derive them)
---------------------------------------------------------------------
Base `https://bipadportal.gov.np/api/v1/`, open, no key, no rate limit
published. Endpoints used here: `incident`, `loss`, `hazard`, `province`,
`district`, `municipality`, `ward`, `river`, `rain`, `earthquake`, `alert`.

* `/incident/` accepts `incident_on__gt` / `incident_on__lt` (dates) and
  `ordering=incident_on`, so a refresh fetches only what is new.
* `?expand=loss` inlines the whole loss record, which turns one request per
  incident into none. Losses carry deaths, missing and injured **split by sex
  and by disability**, families affected/relocated/evacuated, livestock, houses,
  roads, bridges, electricity, and economic loss.
* Earliest incident is 2011-04-14; the collection is smaller than 90,000.

THE PAGING TRAP
---------------
Every list response reports `"count": 9223372036854775807` — the maximum 64-bit
integer, i.e. the portal does not count its rows. A client that trusts `count`
will page forever. Stop when a page comes back empty, which is what
`fetch_all` does, and never present that number to a reader as a total.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

API_BASE = "https://bipadportal.gov.np/api/v1"
DATASET_CODE = "bipad"

TIMEOUT_S = 60
PAGE_SIZE = 500
RETRY_WAIT_S = 5.0
REQUEST_PAUSE_S = 0.3  # a government portal on modest hosting; do not hammer it
# A stop that is generous against the verified <90,000 incidents but still
# refuses to loop forever if the portal's paging ever misbehaves.
MAX_PAGES = 500

# The sentinel BIPAD returns instead of counting. Never treat it as a total.
UNCOUNTED = 9223372036854775807


class BipadError(Exception):
    """The portal did not give us something we can trust."""


@dataclass(frozen=True)
class Page:
    """One page of results, with the untouched bytes it arrived as."""

    url: str
    results: list[dict[str, Any]]
    raw: bytes


def _get(path: str, params: dict[str, Any]) -> Page:
    """One request. Retries once on a transport error, never on a real answer."""
    url = f"{API_BASE}/{path.strip('/')}/"
    for attempt in (1, 2):
        try:
            response = requests.get(url, params=params, timeout=TIMEOUT_S)
        except requests.RequestException as exc:
            if attempt == 2:
                raise BipadError(f"{path}: {type(exc).__name__} after a retry: {exc}") from exc
            print(f"    network error ({type(exc).__name__}); retrying in {RETRY_WAIT_S:.0f}s")
            time.sleep(RETRY_WAIT_S)
            continue

        if response.status_code != 200:
            raise BipadError(f"{path}: HTTP {response.status_code} from {response.url}")
        raw = response.content
        try:
            payload = response.json()
        except ValueError as exc:
            raise BipadError(f"{path}: response was not JSON ({raw[:120]!r})") from exc
        if not isinstance(payload, dict) or "results" not in payload:
            raise BipadError(f"{path}: no 'results' in the response ({sorted(payload)[:6]})")
        results = payload["results"]
        if not isinstance(results, list):
            raise BipadError(f"{path}: 'results' was {type(results).__name__}, not a list")
        return Page(url=response.url, results=results, raw=raw)
    raise AssertionError("unreachable")


def fetch_pages(path: str, params: dict[str, Any] | None = None) -> Iterator[Page]:
    """Every page of one collection, oldest offset first.

    Stops on the first empty page — see THE PAGING TRAP above — and refuses to
    continue past MAX_PAGES rather than spin.
    """
    query = dict(params or {})
    query["limit"] = PAGE_SIZE
    for page_number in range(MAX_PAGES):
        query["offset"] = page_number * PAGE_SIZE
        page = _get(path, query)
        if not page.results:
            return
        yield page
        if len(page.results) < PAGE_SIZE:
            return
        time.sleep(REQUEST_PAUSE_S)
    raise BipadError(
        f"{path}: still returning rows after {MAX_PAGES} pages "
        f"({MAX_PAGES * PAGE_SIZE:,} records) — refusing to page further"
    )


def fetch_all(path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Every record in one collection. Use only where the collection is small
    (hazards, districts, municipalities); incidents are streamed page by page so
    the raw payloads can be archived as they arrive."""
    records: list[dict[str, Any]] = []
    for page in fetch_pages(path, params):
        records.extend(page.results)
    return records


def point_of(record: dict[str, Any]) -> tuple[float, float] | None:
    """(lon, lat) from a BIPAD `point` or `centroid`, or None if absent.

    Returns None rather than a default: an incident without a location must be
    counted as unplaceable, not filed at (0, 0).
    """
    for key in ("point", "centroid"):
        geometry = record.get(key)
        if isinstance(geometry, dict) and geometry.get("type") == "Point":
            coordinates = geometry.get("coordinates")
            if isinstance(coordinates, list) and len(coordinates) == 2:
                lon, lat = coordinates
                if isinstance(lon, int | float) and isinstance(lat, int | float):
                    return float(lon), float(lat)
    return None
