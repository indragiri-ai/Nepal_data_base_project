"""Acquire Ministry of Finance (mof.gov.np) publications — raw-first mirror (MOF.S1).

Crawls each category's public listing and downloads every NEW publication PDF
into the raw lake, untouched, before any parsing (Blueprint raw-first rule).
Two listing layouts exist on this CMS, both handled here:

  - a paginated TABLE (bulletin, budget-speech, redbook, whitebook, yellowbook,
    inter-government-financial-transfer) that embeds the PDF link directly in
    the row, so no extra request is needed per publication;
  - a paginated CARD GRID (economic-survey, half-yearly-elemental-assessment)
    that links only to the content page, where the PDF is inline as
    `var pdf = 'https://giwmscdnone.gov.np/media/pdf_upload/....pdf'` — that
    page is fetched only for entries in this shape.

A manifest at reference/mof/manifest.json is the idempotency ledger (keyed by
the site's own content id): a content id already present is never re-fetched,
so re-running downloads only genuinely new publications. It also carries each
entry's title/date, so `reference/mof/publications_index.csv` can be rebuilt
from it every run (any human-curated `title_en` already in the CSV is carried
forward — see the translation policy in onboard-mof-publications.md).

Published dates are Devanagari BS strings (e.g. "साउन ८, २०८३, शुक्रबार १६:०"
or "१६ भदौ, २०८३"). `parse_bs_date_guess` turns either shape into "YYYY-MM-DD"
(BS) using a fixed Nepali-month-name table — a calendar fact, not a guess —
and returns None for anything it does not recognise, per the report-never-
guess rule; the raw string is always preserved alongside it.

Run with `make mof-acquire`. Options:
    --dry-run              list what would be downloaded, download nothing
    --limit N               stop after N new files (testing)
    --categories a,b,c      restrict to these category slugs (default: all)
    --max-pages N           safety cap on pages scanned per category (default 30)
    --max-mb N              storage soft cap in MB for this run (default 400)
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import certifi
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ingestion.common.io_utf8 import configure_stdout_utf8  # noqa: E402
from ingestion.common.raw_lake import RawLake  # noqa: E402

BASE = "https://mof.gov.np"
CATEGORIES = [
    "bulletin",
    "economic-survey",
    "budget-speech",
    "redbook",
    "whitebook",
    "yellowbook",
    "inter-government-financial-transfer",
    "half-yearly-elemental-assessment",
]
USER_AGENT = "NepalDataPortal/0.1 (data ingestion; contact via mof.gov.np feedback form)"
MANIFEST_PATH = Path("reference/mof/manifest.json")
INDEX_PATH = Path("reference/mof/publications_index.csv")
INDEX_COLUMNS = [
    "content_id",
    "category",
    "title_ne",
    "title_en",
    "published_date_raw",
    "bs_date_guess",
    "pdf_url",
    "sha256",
    "retrieved_at",
]
PDF_CONTENT_TYPE = "application/pdf"
REQUEST_PAUSE_S = 1.5  # politeness (step file: 1-2s delay)
STORAGE_SOFT_CAP_BYTES = 400 * 1024 * 1024  # step file's STOP threshold
MAX_PAGES_DEFAULT = 30
RETRIES = 2

# mof.gov.np's server omits its intermediate certificate from the TLS
# handshake (verified with openssl s_client — see reference/mof/PROVENANCE.md).
# Browsers tolerate this; certifi's strict chain-only validation does not.
# Rather than disable verification, the pinned intermediate is merged into a
# copy of certifi's own bundle, so every host is checked exactly as strictly
# as before, with this one known-missing certificate supplied.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CA_SUPPLEMENT_PATH = _PROJECT_ROOT / "reference/mof/geotrust_tls_rsa_ca_g1.pem"

CONTENT_LINK_RE = re.compile(r"/content/(\d+)/([^/\"]*)/?")
TABLE_ROW_RE = re.compile(
    r'<tr>\s*<td>\d+</td>\s*'
    r'<td>(?P<title>.*?)</td>\s*'
    r'<td>(?P<date>.*?)</td>\s*'
    r'<td>\s*(?:<a href="(?P<pdf_url>[^"]+)"[^>]*>.*?</a>)?\s*</td>\s*'
    r'<td>\s*<a href="\s*(?P<content_href>/content/\d+/[^"]*)\s*"',
    re.S,
)
GRID_CARD_RE = re.compile(
    r'<div class="grid__card">.*?'
    r'<h3 class="card__title">\s*<a href="\s*(?P<content_href>/content/\d+/[^"]*)\s*">'
    r'\s*(?P<title>.*?)\s*</a>\s*</h3>.*?'
    r'<i class="fas fa-clock"></i>\s*(?P<date>.*?)\s*</p>',
    re.S,
)
VAR_PDF_RE = re.compile(r"var pdf\s*=\s*'([^']+)'")
# Every "title-6 translate-title" block on a category page starts a new
# titled section — the real listing is the FIRST one. A later page can also
# carry a "सम्बन्धित" (Related) block using the identical grid__card markup
# but drawn from across the whole site, not this category (verified
# 2026-09-03 on half-yearly-elemental-assessment page 2) — cutting at the
# second heading keeps that noise out.
SECTION_HEADING_RE = re.compile(
    r'<div class="title-6 translate-title">\s*<h2 class="category__title">'
)

DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

# A calendar fact (fixed BS month ordering + the spelling variants this site
# uses), not a guess — see module docstring. Any name not listed here fails
# the parse rather than being approximated.
NEPALI_MONTHS = {
    "बैशाख": 1, "वैशाख": 1,
    "जेठ": 2, "जेष्ठ": 2,
    "असार": 3, "आषाढ": 3, "आषाढ़": 3, "असाढ": 3,
    "साउन": 4, "श्रावण": 4, "श्रावन": 4,
    "भदौ": 5, "भाद्र": 5, "भदो": 5,
    "असोज": 6, "आश्विन": 6,
    "कार्तिक": 7, "कात्तिक": 7,
    "मंसिर": 8, "मार्ग": 8, "मार्गशीर्ष": 8,
    "पुष": 9, "पौष": 9, "पुस": 9,
    "माघ": 10,
    "फागुन": 11, "फाल्गुन": 11,
    "चैत": 12, "चैत्र": 12,
}
MONTH_FIRST_RE = re.compile(r"^(?P<month>[^\d,]+?)\s+(?P<day>[०-९]+),\s*(?P<year>[०-९]+)")
DAY_FIRST_RE = re.compile(r"^(?P<day>[०-९]+)\s+(?P<month>[^\d,]+?),\s*(?P<year>[०-९]+)")


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


def parse_bs_date_guess(raw: str) -> str | None:
    """Deterministically parse a BS date string into 'YYYY-MM-DD' (BS).

    Handles both listing layouts seen on mof.gov.np: month-first
    ("साउन ८, २०८३, शुक्रबार १६:०") and day-first ("१६ भदौ, २०८३"). Anything
    that doesn't match either shape, or names a month outside NEPALI_MONTHS,
    returns None — never guessed.
    """
    if not raw:
        return None
    text = raw.strip()
    m = MONTH_FIRST_RE.match(text) or DAY_FIRST_RE.match(text)
    if not m:
        return None
    month_num = NEPALI_MONTHS.get(m.group("month").strip())
    if month_num is None:
        return None
    try:
        day = int(m.group("day").translate(DEVANAGARI_DIGITS))
        year = int(m.group("year").translate(DEVANAGARI_DIGITS))
    except ValueError:
        return None
    if not (1 <= day <= 32):
        return None
    return f"{year:04d}-{month_num:02d}-{day:02d}"


@dataclass
class Publication:
    content_id: str
    category: str
    slug: str
    title_ne: str
    published_date_raw: str
    bs_date_guess: str | None
    pdf_url: str | None


def extract_primary_section(html: str) -> str:
    """Keep only the first titled section of a category page — the real
    listing — dropping any later same-markup section (e.g. "Related")."""
    starts = [m.start() for m in SECTION_HEADING_RE.finditer(html)]
    if not starts:
        return html
    end = starts[1] if len(starts) > 1 else len(html)
    return html[starts[0] : end]


def discover_pagination_max(html: str) -> int:
    pages = [int(p) for p in re.findall(r"\?page=(\d+)", extract_primary_section(html))]
    return max(pages) if pages else 1


def parse_table_rows(html: str, category: str) -> list[Publication]:
    out = []
    for m in TABLE_ROW_RE.finditer(extract_primary_section(html)):
        cm = CONTENT_LINK_RE.search(m.group("content_href"))
        if not cm:
            continue
        date_raw = clean_text(m.group("date"))
        out.append(
            Publication(
                content_id=cm.group(1),
                category=category,
                slug=cm.group(2),
                title_ne=clean_text(m.group("title")),
                published_date_raw=date_raw,
                bs_date_guess=parse_bs_date_guess(date_raw),
                pdf_url=m.group("pdf_url"),
            )
        )
    return out


def parse_grid_cards(html: str, category: str) -> list[Publication]:
    out = []
    for m in GRID_CARD_RE.finditer(extract_primary_section(html)):
        cm = CONTENT_LINK_RE.search(m.group("content_href"))
        if not cm:
            continue
        date_raw = clean_text(m.group("date"))
        out.append(
            Publication(
                content_id=cm.group(1),
                category=category,
                slug=cm.group(2),
                title_ne=clean_text(m.group("title")),
                published_date_raw=date_raw,
                bs_date_guess=parse_bs_date_guess(date_raw),
                pdf_url=None,
            )
        )
    return out


def parse_listing(html: str, category: str) -> list[Publication]:
    """Table layout is tried first (cheaper: the PDF link is already in it);
    a category with no table rows uses the card-grid layout instead."""
    rows = parse_table_rows(html, category)
    return rows if rows else parse_grid_cards(html, category)


def build_session() -> requests.Session:
    """A Session trusting certifi's bundle plus the pinned GeoTrust
    intermediate mof.gov.np's server omits (see reference/mof/PROVENANCE.md
    and the CA_SUPPLEMENT_PATH comment above) — every other host is verified
    exactly as strictly as plain certifi would verify it."""
    merged = Path(tempfile.gettempdir()) / "mof_acquire_ca_bundle.pem"
    merged.write_bytes(Path(certifi.where()).read_bytes() + b"\n" + CA_SUPPLEMENT_PATH.read_bytes())
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    session.verify = str(merged)
    return session


def fetch_text(session: requests.Session, url: str, retries: int = RETRIES) -> str:
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = session.get(url, timeout=60)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(3 * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def fetch_bytes(session: requests.Session, url: str, retries: int = RETRIES) -> bytes:
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = session.get(url, timeout=120)
            resp.raise_for_status()
            return resp.content
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(3 * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def crawl_category(session: requests.Session, category: str, max_pages: int) -> list[Publication]:
    found: dict[str, Publication] = {}
    first_html = fetch_text(session, f"{BASE}/category/{category}/")
    max_page = min(discover_pagination_max(first_html), max_pages)
    for page in range(1, max_page + 1):
        page_url = f"{BASE}/category/{category}/?page={page}"
        html = first_html if page == 1 else fetch_text(session, page_url)
        pubs = parse_listing(html, category)
        if not pubs and page > 1:
            break
        for p in pubs:
            found.setdefault(p.content_id, p)
        if page > 1:
            time.sleep(REQUEST_PAUSE_S)
    return list(found.values())


def resolve_pdf_url(session: requests.Session, pub: Publication) -> str | None:
    if pub.pdf_url:
        return pub.pdf_url
    html = fetch_text(session, f"{BASE}/content/{pub.content_id}/{pub.slug}/")
    m = VAR_PDF_RE.search(html)
    return m.group(1) if m else None


def load_manifest() -> dict[str, dict[str, Any]]:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {}


def save_manifest(manifest: dict[str, dict[str, Any]]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_existing_title_en() -> dict[str, str]:
    """Preserve human-curated English titles across a manifest rebuild."""
    if not INDEX_PATH.exists():
        return {}
    with INDEX_PATH.open(encoding="utf-8", newline="") as f:
        return {
            row["content_id"]: row["title_en"] for row in csv.DictReader(f) if row.get("title_en")
        }


def write_index(manifest: dict[str, dict[str, Any]]) -> None:
    preserved_title_en = load_existing_title_en()
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with INDEX_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=INDEX_COLUMNS)
        writer.writeheader()
        for content_id in sorted(manifest, key=int):
            e = manifest[content_id]
            writer.writerow(
                {
                    "content_id": content_id,
                    "category": e.get("category", ""),
                    "title_ne": e.get("title_ne", ""),
                    "title_en": preserved_title_en.get(content_id, ""),
                    "published_date_raw": e.get("published_date_raw", ""),
                    "bs_date_guess": e.get("bs_date_guess") or "",
                    "pdf_url": e.get("pdf_url") or "",
                    "sha256": e.get("sha256") or "",
                    "retrieved_at": e.get("fetched_at") or "",
                }
            )


def main() -> None:
    configure_stdout_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--categories", type=str, default=None)
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES_DEFAULT)
    parser.add_argument(
        "--max-mb",
        type=int,
        default=STORAGE_SOFT_CAP_BYTES // (1024 * 1024),
        help="storage soft cap in MB for this run (default: the step file's 400MB)",
    )
    args = parser.parse_args()
    cap_bytes = args.max_mb * 1024 * 1024

    categories = args.categories.split(",") if args.categories else CATEGORIES

    session = build_session()

    manifest = load_manifest()
    existing_bytes = sum(int(e.get("size_bytes", 0)) for e in manifest.values())

    all_pubs: list[Publication] = []
    counts_by_category: dict[str, int] = {}
    for category in categories:
        print(f"Scanning category '{category}'...")
        pubs = crawl_category(session, category, args.max_pages)
        counts_by_category[category] = len(pubs)
        print(f"  {len(pubs)} publication(s) found")
        all_pubs.extend(pubs)
        time.sleep(REQUEST_PAUSE_S)

    new_pubs = [p for p in all_pubs if p.content_id not in manifest]
    print(
        f"Total: {len(all_pubs)} publications across {len(categories)} categories "
        f"({', '.join(f'{k}={v}' for k, v in counts_by_category.items())}), {len(new_pubs)} new."
    )

    if args.dry_run:
        for p in new_pubs:
            print(f"  would download: [{p.category}] {p.content_id} {p.title_ne}")
        return

    lake = RawLake.from_env()
    stored = 0
    skipped_no_pdf = 0
    running_bytes = existing_bytes
    stopped_for_cap = False

    for p in new_pubs:
        if args.limit is not None and stored >= args.limit:
            break

        pdf_url = resolve_pdf_url(session, p)
        if not pdf_url:
            print(f"  SKIP {p.content_id} ({p.category}): no PDF found on its content page")
            manifest[p.content_id] = {
                "category": p.category,
                "slug": p.slug,
                "title_ne": p.title_ne,
                "published_date_raw": p.published_date_raw,
                "bs_date_guess": p.bs_date_guess,
                "pdf_url": None,
                "sha256": None,
                "size_bytes": 0,
                "fetched_at": None,
            }
            save_manifest(manifest)
            skipped_no_pdf += 1
            continue

        payload = fetch_bytes(session, pdf_url)
        if running_bytes + len(payload) > cap_bytes:
            stopped_for_cap = True
            print(
                f"STOP: downloading {p.content_id} would push the MoF mirror past the "
                f"{args.max_mb} MB soft cap "
                f"({running_bytes / 1e6:.1f} MB stored so far). Remaining publications not fetched."
            )
            break

        obj = lake.store(
            dataset_code=f"mof/{p.category}/{p.content_id}",
            payload=payload,
            source_url=pdf_url,
            content_type=PDF_CONTENT_TYPE,
            payload_filename="payload.pdf",
        )
        manifest[p.content_id] = {
            "category": p.category,
            "slug": p.slug,
            "title_ne": p.title_ne,
            "published_date_raw": p.published_date_raw,
            "bs_date_guess": p.bs_date_guess,
            "pdf_url": pdf_url,
            "sha256": obj.sha256,
            "size_bytes": obj.size_bytes,
            "fetched_at": obj.fetched_at,
            "payload_path": obj.payload_path,
            "metadata_path": obj.metadata_path,
        }
        save_manifest(manifest)  # after every file: a crash loses nothing
        write_index(manifest)
        running_bytes += obj.size_bytes
        stored += 1
        print(f"  stored [{p.category}] {p.content_id}: {p.title_ne} ({obj.size_bytes:,} bytes)")
        time.sleep(REQUEST_PAUSE_S)

    write_index(manifest)
    total_mb = running_bytes / (1024 * 1024)
    print(
        f"Done. {stored} new file(s) stored, {skipped_no_pdf} skipped (no PDF); "
        f"manifest now records {len(manifest)} publication(s); "
        f"mirror size ~{total_mb:.1f} MB of the {args.max_mb} MB soft cap. "
        "Idempotent: re-running downloads only genuinely new publications."
    )
    if stopped_for_cap:
        print(
            "STOPPED EARLY: storage soft cap reached before all categories were fully mirrored. "
            "Review reference/mof/publications_index.csv and propose category priorities "
            "to the founder."
        )


if __name__ == "__main__":
    main()
