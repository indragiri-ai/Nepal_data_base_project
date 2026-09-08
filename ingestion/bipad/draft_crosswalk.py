"""Build the BIPAD → P-code crosswalk from evidence, for human review.

A one-off tool, not part of any pipeline. It writes two files:

  db/seeds/bipad_geography_crosswalk.csv     what it could resolve
  reference/bipad/crosswalk_unresolved.csv   what a human must decide

WHY IT IS NOT A NAME MATCH
--------------------------
BIPAD names places its own way. Measured on 2026-09-07: of its 774
"municipalities", only 554 carry a name our gazetteer also uses within the same
district — "Phaktanglung" against our "Phaktanlung", "Solududhkunda" against
"Solu Dudhkunda", and 197 more. Fuzzy-matching those would be guessing, which
this project forbids (CLAUDE.md rule 1).

So each place is resolved twice, independently:

  by NAME     exact match, within the district, after stripping case and
              punctuation only
  by BOUNDARY the place's own centroid, tested against the official boundary
              the website itself draws (ingestion/common/geo_point.py)

and the result is recorded with which evidence supported it:

  both        the two methods agree — the strongest case
  boundary    only the location resolved it (the usual transliteration case)
  name        only the name resolved it (no centroid published)

**Any place where the two methods DISAGREE is never written to the seed.** It
goes to the unresolved file for a person to settle. On the run of 2026-09-07
there were zero disagreements across 753 municipalities, which is the reason to
trust the boundary method at all.

THE 21 THAT ARE NOT MUNICIPALITIES
----------------------------------
BIPAD lists 774 "municipalities" where Nepal has 753. The extra 21 are national
parks, wildlife reserves and hunting reserves — Chitwan National Park, Koshi
Tappu Wildlife Reserve, Dhorpatan Hunting Reserve and so on. They are protected
areas, not local units, and no P-code exists for them. They are written to the
unresolved file with that reason, and incidents inside them are placed by the
incident's OWN coordinates instead, which is more accurate anyway.

Run:  python -m ingestion.bipad.draft_crosswalk [--cache DIR]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ingestion.bipad.client import fetch_all, point_of  # noqa: E402
from ingestion.common.geo_point import BoundaryIndex  # noqa: E402
from ingestion.common.io_utf8 import configure_stdout_utf8  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SEEDS = PROJECT_ROOT / "db" / "seeds"
CROSSWALK_CSV = SEEDS / "bipad_geography_crosswalk.csv"
OVERRIDES_CSV = SEEDS / "bipad_geography_overrides.csv"
UNRESOLVED_CSV = PROJECT_ROOT / "reference" / "bipad" / "crosswalk_unresolved.csv"

CROSSWALK_FIELDS = [
    "bipad_level",
    "bipad_id",
    "bipad_code",
    "bipad_title_en",
    "geography_code",
    "geography_name_en",
    "evidence",
]
UNRESOLVED_FIELDS = ["bipad_level", "bipad_id", "bipad_title_en", "reason", "detail"]

# The known, expected non-municipalities. Naming them lets the report separate
# "we understand why this did not resolve" from "something new has appeared and
# a person should look". BIPAD lists 774 municipalities where Nepal has 753; on
# 2026-09-07 every one of the 21 extras matched one of these.
PROTECTED_AREA = re.compile(
    r"national park|wildlife reserve|hunting reserve|conservation area", re.IGNORECASE
)
# Special administrative areas that are not local units and match no pattern.
# Checked by hand, one at a time — never widened to a loose rule like
# "development area", which would swallow real municipalities.
KNOWN_SPECIAL_AREAS = frozenset({"lumbini sanskritik development area"})


def _is_known_non_municipality(title: str) -> bool:
    return bool(PROTECTED_AREA.search(title)) or title.strip().lower() in KNOWN_SPECIAL_AREAS


def normalise(name: str) -> str:
    """Case and punctuation only. Never a fuzzy or phonetic transformation."""
    folded = unicodedata.normalize("NFKD", name or "")
    return re.sub(r"[^a-z]", "", folded.lower())


@dataclass(frozen=True)
class Row:
    bipad_level: str
    bipad_id: int
    bipad_code: str
    bipad_title_en: str
    geography_code: str
    geography_name_en: str
    evidence: str


def read_geographies() -> tuple[dict[str, tuple[str, str]], dict[tuple[str, str], tuple[str, str]]]:
    """Our gazetteer, keyed for exact-name lookup.

    Districts by normalised name; local units by (district P-code, normalised
    name), because names repeat — two municipalities are called Triveni.
    """
    districts: dict[str, tuple[str, str]] = {}
    local_units: dict[tuple[str, str], tuple[str, str]] = {}
    with (SEEDS / "geographies.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = normalise(row["name_en"])
            if row["level"] == "district":
                districts[key] = (row["code"], row["name_en"])
            elif row["level"] == "local_unit":
                local_units[(row["parent_code"], key)] = (row["code"], row["name_en"])
    return districts, local_units


def _load(cache: Path | None, name: str, path: str) -> list[dict[str, Any]]:
    """BIPAD's list for `path`, from the cache if one was given.

    The cache exists so this tool can be re-run while a person edits the
    unresolved file, without asking the portal for the same 774 rows again.
    """
    if cache:
        cached = cache / f"{name}.json"
        if cached.exists():
            print(f"  {name}: from cache {cached}")
            return list(json.loads(cached.read_text(encoding="utf-8")))
    print(f"  {name}: fetching from BIPAD")
    records = fetch_all(path)
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
        (cache / f"{name}.json").write_text(
            json.dumps(records, ensure_ascii=False), encoding="utf-8"
        )
    return records


def build(cache: Path | None = None) -> tuple[list[Row], list[dict[str, str]]]:
    districts_by_name, local_units_by_name = read_geographies()
    district_boundaries = BoundaryIndex.for_level("district")
    local_boundaries = BoundaryIndex.for_level("local_unit")

    bipad_districts = _load(cache, "districts", "district")
    bipad_municipalities = _load(cache, "municipality", "municipality")

    rows: list[Row] = []
    unresolved: list[dict[str, str]] = []

    # Districts first: a municipality's district is what scopes its name lookup.
    district_pcode: dict[int, str] = {}
    for record in bipad_districts:
        title = record.get("title_en") or record.get("title") or ""
        by_name = districts_by_name.get(normalise(title))
        point = point_of(record)
        by_boundary = district_boundaries.locate(*point) if point else None
        resolved = _decide(
            level="district",
            record=record,
            title=title,
            by_name=by_name[0] if by_name else None,
            by_boundary=by_boundary,
            name_of=lambda code: _name_of(code, districts_by_name),
            rows=rows,
            unresolved=unresolved,
        )
        if resolved:
            district_pcode[int(record["id"])] = resolved

    for record in bipad_municipalities:
        title = record.get("title_en") or record.get("title") or ""
        parent = district_pcode.get(int(record.get("district") or 0))
        by_name_entry = local_units_by_name.get((parent, normalise(title))) if parent else None
        point = point_of(record)
        by_boundary = local_boundaries.locate(*point) if point else None
        _decide(
            level="municipality",
            record=record,
            title=title,
            by_name=by_name_entry[0] if by_name_entry else None,
            by_boundary=by_boundary,
            name_of=lambda code: _name_of(code, local_units_by_name),
            rows=rows,
            unresolved=unresolved,
        )

    rows, unresolved = _reject_contested(rows, unresolved)
    rows = _apply_overrides(rows, local_units_by_name, districts_by_name)
    return rows, unresolved


def _reject_contested(
    rows: list[Row], unresolved: list[dict[str, str]]
) -> tuple[list[Row], list[dict[str, str]]]:
    """Two places cannot be the same place.

    A boundary can mislead as well as decide: BIPAD publishes a centroid for
    "Yemunamai" that falls inside neighbouring Durga Bhagawati's polygon, so
    both resolved to one municipality and the real Yamunamai was left with
    none. Whenever two places claim one geography, NEITHER is trusted — both go
    to a person, and the answer comes back through the overrides file.
    """
    claims: dict[tuple[str, str], list[Row]] = {}
    for row in rows:
        claims.setdefault((row.bipad_level, row.geography_code), []).append(row)
    contested = {key for key, group in claims.items() if len(group) > 1}
    if not contested:
        return rows, unresolved
    kept = [row for row in rows if (row.bipad_level, row.geography_code) not in contested]
    for key in sorted(contested):
        rivals = claims[key]
        names = ", ".join(f"{r.bipad_title_en} (bipad {r.bipad_id})" for r in rivals)
        for row in rivals:
            unresolved.append(
                {
                    "bipad_level": row.bipad_level,
                    "bipad_id": str(row.bipad_id),
                    "bipad_title_en": row.bipad_title_en,
                    "reason": "two places resolve to the same geography",
                    "detail": f"{key[1]} claimed by {names}",
                }
            )
    return kept, unresolved


def _apply_overrides(
    rows: list[Row],
    local_units_by_name: dict[tuple[str, str], tuple[str, str]],
    districts_by_name: dict[str, tuple[str, str]],
) -> list[Row]:
    """Decisions a person made, laid over what the evidence could resolve.

    Kept in its own file so that re-running this tool never silently discards
    human judgement, and so a reader can see exactly which rows are judgement
    rather than measurement.
    """
    if not OVERRIDES_CSV.exists():
        return rows
    by_key = {(row.bipad_level, row.bipad_id): row for row in rows}
    with OVERRIDES_CSV.open(encoding="utf-8") as handle:
        for override in csv.DictReader(handle):
            key = (override["bipad_level"], int(override["bipad_id"]))
            name = _name_of(
                override["geography_code"],
                local_units_by_name if key[0] == "municipality" else districts_by_name,
            )
            by_key[key] = Row(
                bipad_level=override["bipad_level"],
                bipad_id=int(override["bipad_id"]),
                bipad_code=override.get("bipad_code", ""),
                bipad_title_en=override["bipad_title_en"],
                geography_code=override["geography_code"],
                geography_name_en=name,
                evidence="manual_review",
            )
    return list(by_key.values())


def _name_of(code: str, index: dict[Any, tuple[str, str]]) -> str:
    for value in index.values():
        if value[0] == code:
            return value[1]
    return ""


def _decide(
    *,
    level: str,
    record: dict[str, Any],
    title: str,
    by_name: str | None,
    by_boundary: str | None,
    name_of: Any,
    rows: list[Row],
    unresolved: list[dict[str, str]],
) -> str | None:
    """Record one place, or send it to a human. Never split the difference."""
    if by_name and by_boundary and by_name != by_boundary:
        unresolved.append(
            {
                "bipad_level": level,
                "bipad_id": str(record["id"]),
                "bipad_title_en": title,
                "reason": "name and boundary disagree",
                "detail": f"name says {by_name}, centroid falls in {by_boundary}",
            }
        )
        return None
    code = by_name or by_boundary
    if code is None:
        reason = (
            "not a local unit (protected or special area)"
            if _is_known_non_municipality(title)
            else "no name match and no boundary hit"
        )
        unresolved.append(
            {
                "bipad_level": level,
                "bipad_id": str(record["id"]),
                "bipad_title_en": title,
                "reason": reason,
                "detail": f"bipad code {record.get('code', '')}",
            }
        )
        return None
    evidence = "both" if by_name and by_boundary else ("name" if by_name else "boundary")
    rows.append(
        Row(
            bipad_level=level,
            bipad_id=int(record["id"]),
            bipad_code=str(record.get("code") or ""),
            bipad_title_en=title,
            geography_code=code,
            geography_name_en=name_of(code),
            evidence=evidence,
        )
    )
    return code


def write(rows: list[Row], unresolved: list[dict[str, str]]) -> None:
    CROSSWALK_CSV.parent.mkdir(parents=True, exist_ok=True)
    UNRESOLVED_CSV.parent.mkdir(parents=True, exist_ok=True)
    with CROSSWALK_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CROSSWALK_FIELDS)
        writer.writeheader()
        for row in sorted(rows, key=lambda r: (r.bipad_level, r.geography_code)):
            writer.writerow(row.__dict__)
    with UNRESOLVED_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=UNRESOLVED_FIELDS)
        writer.writeheader()
        for item in sorted(unresolved, key=lambda r: (r["reason"], r["bipad_title_en"])):
            writer.writerow(item)


def main() -> int:
    configure_stdout_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache", type=Path, default=None, help="directory to cache BIPAD's lists in"
    )
    args = parser.parse_args()

    rows, unresolved = build(args.cache)
    write(rows, unresolved)

    by_evidence: dict[str, int] = {}
    for row in rows:
        by_evidence[row.evidence] = by_evidence.get(row.evidence, 0) + 1
    by_reason: dict[str, int] = {}
    for item in unresolved:
        by_reason[item["reason"]] = by_reason.get(item["reason"], 0) + 1

    print(f"\nresolved {len(rows)} places -> {CROSSWALK_CSV.relative_to(PROJECT_ROOT)}")
    for evidence, count in sorted(by_evidence.items()):
        print(f"    {evidence:10s} {count:5d}")
    print(f"\nunresolved {len(unresolved)} -> {UNRESOLVED_CSV.relative_to(PROJECT_ROOT)}")
    for reason, count in sorted(by_reason.items()):
        print(f"    {count:5d}  {reason}")

    disagreements = by_reason.get("name and boundary disagree", 0)
    if disagreements:
        print(
            f"\n{disagreements} place(s) where the name and the location contradict each other. "
            "Settle those by hand before loading any incident data."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
