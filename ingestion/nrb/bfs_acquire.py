"""Acquire NRB "Banking and Financial Statistics — Monthly" Excel files (raw-first).

Walks the NRB monthly-statistics archive listing (department=bfr), finds every
directly-linked .xlsx, and stores each NEW file untouched in the raw lake with
its SHA-256, fetch time, and source URL — BEFORE any parsing (Blueprint §2.2).

A manifest at reference/nrb/bfs_manifest.json records every acquired file
(source filename -> sha256, raw-lake paths, source URL). The manifest is the
idempotency ledger: a URL already present is skipped, so re-running downloads
only genuinely new months. It is committed to git as the acquisition record.

Coverage note (recon 2026-07-10): direct .xlsx links exist from Ashadh 2078
(Mid-July 2021) onward — 59 files at recon time. Older reports (2011-2021)
sit behind a JavaScript viewer and are out of scope for this acquirer.

Run with `make nrb-bfs-acquire`. Options:
    --dry-run       list what would be downloaded, download nothing
    --limit N       stop after N new files (testing)
    --max-pages N   listing pages to scan (default 25; scanning stops at the
                    first page with no direct .xlsx links, where the JS-viewer
                    era begins)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ingestion.common.io_utf8 import configure_stdout_utf8  # noqa: E402
from ingestion.common.raw_lake import RawLake  # noqa: E402

LISTING_FIRST = "https://www.nrb.org.np/category/monthly-statistics/?department=bfr"
LISTING_PAGED = "https://www.nrb.org.np/category/monthly-statistics/page/{page}/?department=bfr"
XLSX_LINK_RE = re.compile(r'href="(https://www\.nrb\.org\.np/contents/uploads/[^"]+\.xlsx?)"')
USER_AGENT = "NepalDataPortal/0.1 (data ingestion; contact via nrb.org.np feedback form)"
MANIFEST_PATH = Path("reference/nrb/bfs_manifest.json")
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
REQUEST_PAUSE_S = 0.5  # be polite to the NRB webserver


def load_manifest() -> dict[str, dict[str, str | int]]:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {}


def save_manifest(manifest: dict[str, dict[str, str | int]]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def discover_xlsx_urls(session: requests.Session, max_pages: int) -> list[str]:
    """Scan listing pages newest-first; stop at the first page without direct
    .xlsx links (that is where the pre-2021 JS-viewer era begins)."""
    urls: list[str] = []
    for page in range(1, max_pages + 1):
        url = LISTING_FIRST if page == 1 else LISTING_PAGED.format(page=page)
        resp = session.get(url, timeout=60)
        if resp.status_code == 404:  # ran past the last archive page
            break
        resp.raise_for_status()
        found = XLSX_LINK_RE.findall(resp.text)
        if not found:
            break
        for u in found:
            if u not in urls:
                urls.append(u)
        time.sleep(REQUEST_PAUSE_S)
    return urls


def main() -> None:
    configure_stdout_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-pages", type=int, default=25)
    args = parser.parse_args()

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    manifest = load_manifest()
    urls = discover_xlsx_urls(session, args.max_pages)
    new_urls = [u for u in urls if u.rsplit("/", 1)[-1] not in manifest]
    print(f"Listing scan: {len(urls)} direct .xlsx links, {len(new_urls)} new.")

    if args.dry_run:
        for u in new_urls:
            print("  would download:", u)
        return

    lake = RawLake.from_env()
    stored = 0
    for url in new_urls:
        if args.limit is not None and stored >= args.limit:
            break
        filename = url.rsplit("/", 1)[-1]
        resp = session.get(url, timeout=120)
        resp.raise_for_status()
        payload = resp.content
        # Raw-lake path keyed by the source's own filename (Phase-1 Lesson c).
        obj = lake.store(
            dataset_code=f"nrb/bfs/{Path(filename).stem}",
            payload=payload,
            source_url=url,
            content_type=XLSX_CONTENT_TYPE,
            payload_filename="payload.xlsx",
        )
        manifest[filename] = {
            "source_url": url,
            "sha256": obj.sha256,
            "size_bytes": obj.size_bytes,
            "fetched_at": obj.fetched_at,
            "payload_path": obj.payload_path,
            "metadata_path": obj.metadata_path,
        }
        save_manifest(manifest)  # after every file: a crash loses nothing
        stored += 1
        print(f"  stored {filename} ({obj.size_bytes:,} bytes, sha256 {obj.sha256[:12]}…)")
        time.sleep(REQUEST_PAUSE_S)

    print(
        f"Done. {stored} new file(s) stored in the raw lake; "
        f"manifest now records {len(manifest)} file(s). Idempotent: re-running skips them."
    )


if __name__ == "__main__":
    main()
