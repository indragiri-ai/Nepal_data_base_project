"""Watch the World Bank's Nepal Fiscal Dashboard for updates (WBF.S4).

WHY THIS DOES NOT WATCH A "LAST UPDATED" STRING
-----------------------------------------------
The step file suggests checking the page's "Last Updated" text. That is not
available: the S1 recon established, and `reference/wb-fiscal/PROVENANCE.md`
records, that the page carries no crawlable last-updated string — the recon's
own "Last updated: Feb 12, 2026" could not be re-confirmed from the page text.
Watching a string that is not there would be a watcher that never fires, which
is worse than no watcher, because it looks like one.

So this watches THE DATA. It re-harvests the nine federal aggregate series —
the same `harvest()` the loader uses, so there is no second parser to keep in
step — and reduces them to a small fingerprint: for each series, how many years
it has, which year is newest, and that year's value. If the World Bank revises
a figure, adds a fiscal year, or renames a series, the fingerprint changes.
That is a stronger signal than a date string: it reports what actually moved.

Federal only, deliberately. A full provincial harvest is ~45 minutes and the
provincial sheets ride the same publication cycle; if the dashboard is
refreshed, the federal series move too. Federal is the canary, and it costs
nine requests.

WHAT TO DO WHEN IT FIRES
------------------------
Re-run the load chain — it is idempotent by construction, so re-running is
safe and loads only what actually changed:

    make ingest-wb-fiscal              # federal
    make ingest-wb-fiscal-provincial   # provincial (~45 min)
    make wb-fiscal-watch-update        # accept the new fingerprint

Run with `make wb-fiscal-watch`. Exit code 0 = unchanged, 1 = changed (that is
what turns the scheduled workflow red and opens an issue), 2 = the check could
not run at all.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ingestion.common.io_utf8 import configure_stdout_utf8  # noqa: E402
from ingestion.worldbank.fiscal_pipeline import Row, harvest  # noqa: E402

FINGERPRINT_PATH = Path("reference/wb-fiscal/watch_fingerprint.json")

# Every period label this source produces has the shape "FY 2023/24"
# (dashboard_year_to_period_label builds them). Within one fixed shape, sorting
# the label as text and sorting it chronologically are the same thing — but
# only within one shape, so an unexpected label stops the run instead of
# silently picking the wrong "newest" year.
LABEL_RE = re.compile(r"^FY (\d{4})/\d{2}$")


class FiscalWatchError(Exception):
    """The check could not be completed — not the same thing as a change."""


def period_year(label: str) -> int:
    match = LABEL_RE.match(label)
    if match is None:
        raise FiscalWatchError(
            f"unexpected period label {label!r}: expected the form 'FY 2023/24'. "
            "The source's year labelling changed — check the layout module "
            "before trusting any comparison."
        )
    return int(match.group(1))


def fingerprint(rows: list[Row]) -> dict[str, dict[str, str]]:
    """Reduce a harvest to the smallest thing that still notices a change.

    Per series: how many years it carries, its newest year, and that year's
    value. A revision to an older year moves nothing here — that is the one
    blind spot, and it is accepted deliberately: keeping every value would make
    this a second copy of the warehouse, which is the thing the warehouse is
    for. The load chain is idempotent, so a re-run after any fire picks up
    older revisions anyway.
    """
    by_code: dict[str, list[Row]] = {}
    for row in rows:
        by_code.setdefault(row.indicator_code, []).append(row)

    out: dict[str, dict[str, str]] = {}
    for code, series in sorted(by_code.items()):
        latest = max(series, key=lambda r: period_year(r.period_label))
        out[code] = {
            "years": str(len(series)),
            "latest_period": latest.period_label,
            "latest_value": str(latest.value),
        }
    return out


def describe_changes(
    old: dict[str, dict[str, str]], new: dict[str, dict[str, str]]
) -> list[str]:
    """Plain-language lines naming what moved. Empty list = nothing moved."""
    lines: list[str] = []

    for code in sorted(set(new) - set(old)):
        lines.append(f"NEW SERIES  {code}: {new[code]['years']} years, "
                     f"latest {new[code]['latest_period']}")
    for code in sorted(set(old) - set(new)):
        lines.append(f"SERIES GONE {code}: was {old[code]['years']} years, "
                     f"latest {old[code]['latest_period']} — the sheet may have "
                     "been renamed or withdrawn")

    for code in sorted(set(old) & set(new)):
        before, after = old[code], new[code]
        if before["latest_period"] != after["latest_period"]:
            lines.append(
                f"NEW YEAR    {code}: {before['latest_period']} -> "
                f"{after['latest_period']} (value {after['latest_value']})"
            )
        elif before["latest_value"] != after["latest_value"]:
            lines.append(
                f"REVISED     {code} {after['latest_period']}: "
                f"{before['latest_value']} -> {after['latest_value']}"
            )
        elif before["years"] != after["years"]:
            lines.append(
                f"YEAR COUNT  {code}: {before['years']} -> {after['years']} years"
            )
    return lines


def read_stored(path: Path) -> dict[str, dict[str, str]] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FiscalWatchError(f"{path} is not valid JSON: {exc}") from exc
    series = data.get("series")
    if not isinstance(series, dict):
        raise FiscalWatchError(f"{path} has no 'series' object — refusing to compare.")
    return series


def write_stored(path: Path, series: dict[str, dict[str, str]], checked_at: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_what": "Fingerprint of the World Bank Nepal Fiscal Dashboard's federal "
                 "series. Compared on a schedule by ingestion/worldbank/"
                 "fiscal_watch.py; a difference means the source published "
                 "something new. Update it only after re-running the load.",
        "checked_at": checked_at,
        "series": series,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    configure_stdout_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update",
        action="store_true",
        help="accept the current source state as the new baseline",
    )
    args = parser.parse_args()

    from datetime import date

    print("Checking the World Bank Nepal Fiscal Dashboard (9 federal series)…")
    rows = harvest()
    current = fingerprint(rows)
    print(f"Fingerprinted {len(current)} series.")

    stored = read_stored(FINGERPRINT_PATH)

    if args.update:
        write_stored(FINGERPRINT_PATH, current, date.today().isoformat())
        print(f"Baseline written to {FINGERPRINT_PATH}.")
        return 0

    if stored is None:
        write_stored(FINGERPRINT_PATH, current, date.today().isoformat())
        print(
            f"No baseline existed; wrote one to {FINGERPRINT_PATH}. "
            "Nothing to compare against yet."
        )
        return 0

    changes = describe_changes(stored, current)
    if not changes:
        print("No change: the dashboard's federal series are as last recorded.")
        return 0

    print(f"\nTHE SOURCE CHANGED — {len(changes)} difference(s):\n")
    for line in changes:
        print(f"  {line}")
    print(
        "\nWhat to do: re-run `make ingest-wb-fiscal` and "
        "`make ingest-wb-fiscal-provincial` (both idempotent), then "
        "`make wb-fiscal-watch-update` to accept the new baseline."
    )
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FiscalWatchError as exc:
        print(f"CHECK FAILED: {exc}", file=sys.stderr)
        sys.exit(2)
