"""A reusable CKAN client (ODN.S1).

Open Data Nepal runs CKAN, and so do many other government portals — so this
is written against CKAN, not against Open Data Nepal. Nothing here knows what
a commodity or a price is; that belongs to the dataset-specific loader.

THREE THINGS THIS GUARANTEES
----------------------------
1. **Raw before parsed (rule 3).** `store_raw` archives the untouched page
   payloads AND the `package_show` metadata — licence, organisation, notes,
   modified date — as one immutable snapshot, before anything is interpreted.
   The metadata is the provenance snapshot: a licence that changes later
   cannot quietly rewrite what we were told when we took the data.
2. **Complete pages, or a loud failure.** Datastore paging stops when it has
   `total` rows; if the source stops handing them over early, that is raised,
   not returned as a short list. A silently truncated harvest looks exactly
   like a small dataset.
3. **`success != true` is fatal.** CKAN answers HTTP 200 with
   `{"success": false}` for real errors, so the HTTP status alone is not a
   check.

ON THE AGGREGATOR QUESTION (worth knowing before using this)
------------------------------------------------------------
Open Data Nepal is a distribution channel, not an origin: the authority for a
dataset is the agency that published it. Callers must record the ORIGINATING
agency as the source and ODN as the dataset's access route — see the step file
`docs/steps/onboard-opendatanepal.md`. `fetch_package` returns the metadata a
caller needs to do that honestly (`organization`, `license_id`, `notes`).
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ingestion.common.raw_lake import RawLake, StoredObject  # noqa: E402

API_BASE = "https://api.opendatanepal.com/api/3/action"
DATASET_PREFIX = "opendatanepal"

TIMEOUT_S = 60
PAGE_SIZE = 1000
# One retry, then give up. A source that is down must fail the run rather than
# be retried into a partial harvest.
RETRY_WAIT_S = 5.0
REQUEST_PAUSE_S = 0.5  # be polite: this is a community-run portal


class CkanError(Exception):
    """The portal did not give us something we can trust."""


@dataclass(frozen=True)
class DatastoreResult:
    """Rows parsed out of CKAN, plus the untouched pages they came from."""

    resource_id: str
    total: int
    fields: list[str]
    rows: list[dict[str, Any]]
    pages: list[tuple[str, bytes]]  # (source_url, raw response bytes)


def _call(action: str, params: dict[str, Any]) -> tuple[dict[str, Any], bytes, str]:
    """One CKAN action call. Returns (result, raw bytes, url).

    Retries once on a transport error only. A response that arrives and says
    `success: false` is a decision by the portal, not a blip, so it is raised
    immediately rather than retried.
    """
    url = f"{API_BASE}/{action}"
    for attempt in (1, 2):
        try:
            response = requests.get(url, params=params, timeout=TIMEOUT_S)
        except requests.RequestException as exc:
            if attempt == 2:
                raise CkanError(f"{action}: {type(exc).__name__} after a retry: {exc}") from exc
            print(f"    network error ({type(exc).__name__}); retrying in {RETRY_WAIT_S:.0f}s")
            time.sleep(RETRY_WAIT_S)
            continue

        if response.status_code != 200:
            raise CkanError(
                f"{action}: HTTP {response.status_code} from {response.url}"
            )
        raw = response.content
        try:
            payload = response.json()
        except ValueError as exc:
            raise CkanError(f"{action}: response was not JSON ({raw[:120]!r})") from exc
        if payload.get("success") is not True:
            raise CkanError(
                f"{action}: CKAN reported failure: {payload.get('error') or payload}"
            )
        result = payload.get("result")
        if not isinstance(result, dict):
            raise CkanError(f"{action}: no result object in the response")
        return result, raw, response.url

    raise CkanError(f"{action}: unreachable retry loop")  # pragma: no cover


def fetch_package(dataset_id: str) -> tuple[dict[str, Any], bytes]:
    """`package_show` for one dataset. Returns (metadata, raw bytes)."""
    result, raw, _ = _call("package_show", {"id": dataset_id})
    return result, raw


def search_packages(query: str, rows: int = 20) -> list[dict[str, Any]]:
    """`package_search` — used to find a dataset id from a human phrase."""
    result, _, _ = _call("package_search", {"q": query, "rows": str(rows)})
    results = result.get("results")
    if not isinstance(results, list):
        raise CkanError("package_search: no results list in the response")
    return results


def parse_page(result: dict[str, Any]) -> tuple[int, list[str], list[dict[str, Any]]]:
    """Pull (total, field names, records) out of one datastore page.

    Field names are returned as the source spells them, including when the
    spelling is wrong. The Kalimati 2021+ resource, for example, was uploaded
    without a header row, so CKAN took its first DATA row as the column names
    ('Tomato Big(Nepali)', '2021-01-05 00:00:00', 'Kg', '50', …). Repairing
    that is a decision about one dataset and belongs to that dataset's loader,
    which can verify a mapping against the publishing agency. A generic client
    that quietly renamed columns would hide the problem from the only code in
    a position to check it.
    """
    total = result.get("total")
    if not isinstance(total, int):
        raise CkanError("datastore_search: no integer 'total' in the response")
    fields = [f["id"] for f in result.get("fields", []) if isinstance(f, dict) and "id" in f]
    records = result.get("records")
    if not isinstance(records, list):
        raise CkanError("datastore_search: no records list in the response")
    return total, fields, records


def fetch_datastore_rows(
    resource_id: str, page_size: int = PAGE_SIZE, limit_pages: int | None = None
) -> DatastoreResult:
    """Every row of one datastore resource, paged.

    `limit_pages` stops early — for a probe or a test against a large resource.
    A partial fetch is reported as such by `len(rows) < total`; only a fetch
    that was MEANT to be complete and came up short raises.
    """
    rows: list[dict[str, Any]] = []
    pages: list[tuple[str, bytes]] = []
    total: int | None = None
    fields: list[str] = []
    offset = 0

    while True:
        result, raw, url = _call(
            "datastore_search",
            {"resource_id": resource_id, "limit": str(page_size), "offset": str(offset)},
        )
        page_total, page_fields, records = parse_page(result)
        if total is None:
            total, fields = page_total, page_fields
        pages.append((url, raw))
        rows.extend(records)

        if not records:
            # No progress and not finished: stop rather than loop forever.
            break
        offset += len(records)
        if offset >= total:
            break
        if limit_pages is not None and len(pages) >= limit_pages:
            break
        time.sleep(REQUEST_PAUSE_S)

    if total is None:  # pragma: no cover - the loop always runs once
        raise CkanError(f"{resource_id}: no pages returned")
    if limit_pages is None and len(rows) != total:
        raise CkanError(
            f"{resource_id}: fetched {len(rows)} rows but the portal reports "
            f"{total}. A short harvest is indistinguishable from a small "
            "dataset once loaded, so this stops here."
        )
    return DatastoreResult(
        resource_id=resource_id, total=total, fields=fields, rows=rows, pages=pages
    )


def store_raw(
    lake: RawLake,
    dataset_slug: str,
    result: DatastoreResult,
    package_raw: bytes,
    package_url: str,
) -> StoredObject:
    """Archive the untouched pages + the package metadata as ONE snapshot.

    One object rather than one per page: a 197k-row resource is ~200 pages, and
    the free tier makes each upload expensive (the World Bank catalogue proved
    that — ~4,000 uploads took hours). Every member keeps its own bytes, hash
    and source URL inside the snapshot, so the raw-first guarantee is intact;
    only the granularity changes.
    """
    members: list[tuple[str, bytes, str]] = [
        (f"page_{i:04d}.json", raw, url) for i, (url, raw) in enumerate(result.pages)
    ]
    members.append(("package_show.json", package_raw, package_url))
    return lake.store_snapshot(
        f"{DATASET_PREFIX}/{dataset_slug}/{result.resource_id}", members
    )


def summarise(package: dict[str, Any]) -> str:
    """The authority check, as a printable block (step file: mandatory).

    An aggregator's dataset is only onboardable if it names a real agency and
    carries an open licence; `notspecified` needs founder sign-off. Printing
    this makes that judgement visible instead of buried in a JSON blob.
    """
    org = (package.get("organization") or {}).get("title") or "— none named —"
    licence = package.get("license_id") or "notspecified"
    lines = [
        f"  dataset    : {package.get('name')}",
        f"  title      : {package.get('title')}",
        f"  agency     : {org}",
        f"  licence    : {licence} ({package.get('license_title') or 'no title'})",
        f"  modified   : {package.get('metadata_modified')}",
        f"  resources  : {len(package.get('resources') or [])}",
    ]
    for res in package.get("resources") or []:
        lines.append(
            f"    - {res.get('id')}  datastore_active={res.get('datastore_active')}"
            f"  {res.get('name')}"
        )
    if licence not in ("cc-by", "cc-by-sa", "cc-zero", "odc-by"):
        lines.append(
            f"  WARNING    : licence {licence!r} is not one of the open licences "
            "this project onboards without sign-off."
        )
    return "\n".join(lines)


def _probe(dataset_id: str) -> None:
    """Live check: metadata + the first page of every datastore resource.

    Deliberately does not fetch whole resources — this is the 'is the channel
    alive and shaped as we recorded?' check, not an ingestion.
    """
    package, _ = fetch_package(dataset_id)
    print(summarise(package))
    for res in package.get("resources") or []:
        if not res.get("datastore_active"):
            print(f"\n  {res.get('id')}: datastore not active — skipped")
            continue
        result = fetch_datastore_rows(res["id"], page_size=5, limit_pages=1)
        print(f"\n  resource {res['id']}")
        print(f"    total rows : {result.total:,}")
        print(f"    fields     : {result.fields}")
        if result.rows:
            print(f"    first row  : {json.dumps(result.rows[0], ensure_ascii=False)}")


if __name__ == "__main__":
    from ingestion.common.io_utf8 import configure_stdout_utf8

    configure_stdout_utf8()
    target = sys.argv[1] if len(sys.argv) > 1 else "kalimati-tarkari-dataset"
    print(f"Probing Open Data Nepal for {target!r}…\n")
    try:
        _probe(target)
    except CkanError as exc:
        print(f"\nPROBE FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
