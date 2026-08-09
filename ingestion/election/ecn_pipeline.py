"""ECN.S3 — load party votes and seats for both House of Representatives elections.

WHAT GOES IN
------------
Two indicators, from the endpoints ECN.S1 mapped (`reference/ecn/PROVENANCE.md`):

  ELECTION_VOTES_PR   proportional-representation votes per party
                      · national, and for each of the 77 districts
  ELECTION_SEATS      first-past-the-post seats per party, national

for the elections of **2082 BS (polled 5 March 2026)** and
**2079 BS (polled 20 November 2022)**.

WHAT DELIBERATELY DOES NOT GO IN
--------------------------------
* **Turnout and registered voters.** The Commission does not publish them for
  either election through this channel — see PROVENANCE.md, which records the
  search. The district measure here is votes CAST. It must never be presented
  as turnout: the denominator does not exist in our data.
* **The 110 proportional seats.** They are allocated in a separate published
  notice, not through the results portal. Loading a party's constituency seats
  as if they were its seats in the house would understate every large party.
* **Candidates' personal details.** The source files carry each candidate's
  father's name, spouse, date of birth and home address. Being reachable does
  not make them ours to republish. Only the result is taken.

THE TWO ELECTION DATES ARE SOURCED, NOT ASSUMED
-----------------------------------------------
The results portal names its elections by Bikram Sambat year alone. The polling
dates come from the Commission's own documents and were converted with this
project's BS calendar:

  2082 BS  the ECN's call for international observers (published 28/10/2025)
           states the "House of Representatives Election, 2026" is
           "being held on 5th March, 2026"  ->  2082-11-21 BS, a Thursday
  2079 BS  the ECN's official election programme (FPTP and PR sheets both)
           gives मतदान = 2079-08-04 BS      ->  20 November 2022, a Sunday

WHY THE DISTRICT TOTALS ARE RE-CHECKED HERE
-------------------------------------------
ECN.S1 proved the 77 district files sum exactly to the national figure. That
proof is about the data as it was on one day, not a property of the code, so the
check runs again inside this pipeline and a mismatch **blocks the load**. A
partly-harvested source that quietly loads is how a chart comes to under-report
a party.

Run with `make ecn-load` (add `--dry-run` to write nothing).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ingestion.common.io_utf8 import configure_stdout_utf8  # noqa: E402
from ingestion.common.raw_lake import RawLake, RawLakeError  # noqa: E402
from ingestion.election.ecn_client import EcnClient, EcnError, decode_json  # noqa: E402
from ingestion.election.ecn_probe import HOR_FPTP_SEATS, real_districts  # noqa: E402

SOURCE_NAME = "Election Commission of Nepal"
SOURCE_NAME_NE = "निर्वाचन आयोग, नेपाल"
SOURCE_URL = "https://election.gov.np"
DATASET_NAME = "House of Representatives election results"
DATASET_URL = "https://result.election.gov.np"
# No licence text is published anywhere on the portal. Recorded as that, rather
# than assuming one — these are official public records of a state body.
DATASET_LICENSE = (
    "No licence stated by the publisher; official public records of the "
    "Election Commission of Nepal"
)

DATASET_CODE = "ecn/results"
VOTES_INDICATOR = "ELECTION_VOTES_PR"
SEATS_INDICATOR = "ELECTION_SEATS"
VOTES_UNIT = "VOTES"
SEATS_UNIT = "SEATS"
NATIONAL_GEO = "NP"

SEED_CSV = Path("db/seeds/indicators_election.csv")
DISTRICT_CSV = Path("db/seeds/ecn_district_codes.csv")
PARTY_CSV = Path("reference/ecn/party_names.csv")

# Provenance label for an English party name the Commission itself published
# (its by-election feed carries `PoliticalPartyNameEng`). Anything a human adds
# later gets its own label; the two must never be confused.
ECN_PUBLISHED = "published by the ECN"

BATCH = 500

# How long a session must have sat 'idle in transaction' before we treat it as a
# corpse rather than a slow colleague. Generous on purpose: a healthy pipeline
# pausing between statements over the pooler must never be mistaken for a crash.
STALE_SESSION_SECONDS = 300

# The elections this pipeline knows about: BS year -> (calendar year of polling,
# polling date, the BS polling date). Sourced above; not derived from the data.
ELECTIONS: dict[str, tuple[str, str, str]] = {
    "2082": ("2026", "2026-03-05", "2082-11-21"),
    "2079": ("2022", "2022-11-20", "2079-08-04"),
}


class EcnLoadError(Exception):
    """The load was refused. Nothing is written when this is raised."""


@dataclass
class CycleFacts:
    """Everything one election contributes, already checked for consistency."""

    cycle: str
    pr_national: dict[str, int]
    pr_by_district: dict[int, dict[str, int]]
    seats_fptp: dict[str, int]


def _scalar(cur: psycopg.Cursor[Any]) -> Any:
    row = cur.fetchone()
    return None if row is None else row[0]


def clear_stale_pipeline_sessions(conn: psycopg.Connection[Any]) -> None:
    """Terminate 'idle in transaction' sessions left behind by a crashed run.

    CLAUDE.md rule 8: a run killed mid-transaction leaves a session holding
    locks through the pooler, and the next run simply blocks until statement
    timeout — which reads like a database fault rather than the dead
    predecessor it is. This bit us during ECN.S3 itself: an interrupted seed
    left a session holding `geographies`, and the retry died on a timeout.

    Only our own pipelines and seeds write to these tables, so such a session is
    normally a corpse. Matched on the tables this pipeline touches rather than on
    `observations` alone, because the seed that blocked us was stuck on
    `geographies`.

    **The age guard is not optional.** A pipeline mid-run over the free-tier
    pooler sits 'idle in transaction' for seconds at a time between statements —
    that is what a slow row-by-row loop looks like from outside. A cleaner
    without this guard will happily terminate a healthy run that is simply being
    slow, which is exactly what happened while building this step. Only sessions
    idle far longer than any real gap between statements are touched.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pid, pg_terminate_backend(pid) FROM pg_stat_activity"
            " WHERE datname = current_database() AND pid <> pg_backend_pid()"
            "   AND state = 'idle in transaction'"
            # make_interval, not `interval %s`: Postgres will not accept a
            # parameter where an interval literal is expected.
            "   AND state_change < now() - make_interval(secs => %s)"
            "   AND (query LIKE '%%observations%%' OR query LIKE '%%geographies%%'"
            "        OR query LIKE '%%indicators%%' OR query LIKE '%%releases%%')",
            (STALE_SESSION_SECONDS,),
        )
        cleared = cur.fetchall()
    conn.commit()
    if cleared:
        print(f"  cleared {len(cleared)} stale lock-holding session(s) from a crashed run")


def read_district_map() -> dict[int, str]:
    """ECN district code -> our geography code, from the curated seed.

    Curated by hand and committed, never derived at run time: 72 of the 77 rows
    matched the Commission's Devanagari district name exactly within its
    province, and the remaining 5 differ only by a spelling variant (ब/व, or
    where the halant falls) and were resolved by a human, with the reason
    recorded in the file's `how_matched` column.
    """
    if not DISTRICT_CSV.exists():
        raise EcnLoadError(f"{DISTRICT_CSV} is missing — it is curated reference data.")
    with DISTRICT_CSV.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    mapping = {int(r["ecn_district_cd"]): r["geo_code"] for r in rows}
    if len(mapping) != 77:
        raise EcnLoadError(f"{DISTRICT_CSV}: expected 77 districts, found {len(mapping)}")
    if len(set(mapping.values())) != 77:
        raise EcnLoadError(f"{DISTRICT_CSV}: two ECN codes point at the same geography")
    return mapping


def harvest(client: EcnClient, cycle: str, raw: list[tuple[str, bytes, str]]) -> CycleFacts:
    """Read one election. Every payload read is kept for the raw archive."""

    def grab(path: str) -> Any:
        got = client.fetch(path)
        if not got.is_json:
            raise EcnLoadError(
                f"{path}: the portal returned HTTP {got.status_code} "
                f"({got.content_type or 'no content-type'}). Refusing to load a "
                f"partial election."
            )
        raw.append((path, got.content, got.url))
        return decode_json(got.content)

    pr_national_rows = grab(f"JSONFiles/Election{cycle}/Common/PRHoRPartyTop5.txt")
    seats_rows = grab(f"JSONFiles/Election{cycle}/Common/HoRPartyTop5.txt")
    district_rows = grab(f"JSONFiles/Election{cycle}/Local/Lookup/districts.json")

    pr_national: dict[str, int] = {}
    for r in pr_national_rows:
        name = r["PoliticalPartyName"]
        if name in pr_national:
            raise EcnLoadError(
                f"{cycle}: the national PR file lists {name!r} twice. That is the "
                f"defect PROVENANCE.md records for the 2082 PROVINCIAL files; seeing "
                f"it here means the national file is now affected too. Refusing to load."
            )
        pr_national[name] = int(r["TotalVoteReceived"])

    seats: dict[str, int] = defaultdict(int)
    for r in seats_rows:
        seats[r["PoliticalPartyName"]] += int(r["TotWin"])

    pr_by_district: dict[int, dict[str, int]] = {}
    for district in sorted(d["id"] for d in real_districts(district_rows)):
        rows = grab(f"JSONFiles/Election{cycle}/HOR/PR/District/{district}.json")
        per_party: dict[str, int] = defaultdict(int)
        for r in rows:
            per_party[r["PoliticalPartyName"]] += int(r["TotalVoteReceived"])
        pr_by_district[district] = dict(per_party)

    return CycleFacts(cycle, pr_national, pr_by_district, dict(seats))


def check(facts: CycleFacts) -> None:
    """Refuse the load unless the source agrees with itself. Blocking, by design."""
    cycle = facts.cycle

    if len(facts.pr_by_district) != 77:
        raise EcnLoadError(
            f"{cycle}: read {len(facts.pr_by_district)} district PR files, expected 77. "
            f"A partial read must never be loaded — the totals would silently under-report."
        )

    summed: dict[str, int] = defaultdict(int)
    for per_party in facts.pr_by_district.values():
        for name, votes in per_party.items():
            summed[name] += votes

    national_total = sum(facts.pr_national.values())
    district_total = sum(summed.values())
    if national_total != district_total:
        raise EcnLoadError(
            f"{cycle}: district PR votes total {district_total:,} but the national "
            f"file says {national_total:,} (difference {district_total - national_total:+,}). "
            f"Refusing to load a source that does not reconcile."
        )

    disagreeing = {
        name: (votes, summed.get(name, 0))
        for name, votes in facts.pr_national.items()
        if summed.get(name, 0) != votes
    }
    if disagreeing:
        sample = list(disagreeing.items())[:3]
        raise EcnLoadError(
            f"{cycle}: {len(disagreeing)} parties' district votes do not sum to their "
            f"national figure, e.g. {sample}. Refusing to load."
        )

    seat_total = sum(facts.seats_fptp.values())
    if seat_total != HOR_FPTP_SEATS:
        raise EcnLoadError(
            f"{cycle}: seats total {seat_total}, but the House of Representatives has "
            f"{HOR_FPTP_SEATS} first-past-the-post seats. Refusing to load."
        )

    for name, votes in facts.pr_national.items():
        if votes < 0:
            raise EcnLoadError(f"{cycle}: {name} has a negative vote total ({votes}).")

    print(
        f"  checks passed: {len(facts.pr_national)} parties, "
        f"{national_total:,} PR votes reconciled across 77/77 districts, "
        f"{seat_total} FPTP seats"
    )


def write_party_reference(all_parties: set[str], ecn_english: dict[str, str]) -> None:
    """Record every party name we store, for later human curation.

    English names are written ONLY where the Commission itself supplies one
    (its by-election feed carries `PoliticalPartyNameEng` for a handful of
    parties). The rest are left EMPTY on purpose: transliterating a political
    party's name ourselves would be inventing an official-looking English name
    that no source published. Blank is honest; a guess is not.
    """
    PARTY_CSV.parent.mkdir(parents=True, exist_ok=True)

    # Keep each existing English name TOGETHER WITH the provenance already
    # recorded for it. Re-deriving that provenance on a rewrite is how a name the
    # ECN published gets relabelled "curated by hand" on the second run — which
    # is a false claim that a human checked it. Rewriting this file must never
    # upgrade the standing of a name.
    existing: dict[str, tuple[str, str]] = {}
    if PARTY_CSV.exists():
        with PARTY_CSV.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if row.get("name_en"):
                    existing[row["name_ne"]] = (
                        row["name_en"],
                        row.get("source_of_english", "") or ECN_PUBLISHED,
                    )

    with PARTY_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["name_ne", "name_en", "source_of_english"])
        for name in sorted(all_parties):
            if name in ecn_english:
                # The source itself published it; that always wins and is
                # re-asserted on every run.
                english, source = ecn_english[name], ECN_PUBLISHED
            elif name in existing:
                english, source = existing[name]
            else:
                english, source = "", ""
            writer.writerow([name, english, source])

    with_english = sum(1 for n in all_parties if n in ecn_english or n in existing)
    print(
        f"Party reference written to {PARTY_CSV}: {len(all_parties)} parties, "
        f"{with_english} with an English name, {len(all_parties) - with_english} awaiting curation"
    )


def ensure_source_and_dataset(cur: psycopg.Cursor[Any]) -> int:
    cur.execute(
        "INSERT INTO sources (name_en, name_ne, type, url, default_license, notes)"
        # 'ministry' is the closest value the sources.type CHECK allows. The ECN is
        # a CONSTITUTIONAL COMMISSION, independent of any ministry — the note says
        # so, rather than letting the type column imply otherwise.
        " VALUES (%s, %s, 'ministry', %s, %s, %s)"
        " ON CONFLICT (name_en) DO UPDATE SET name_ne = EXCLUDED.name_ne,"
        "   url = EXCLUDED.url, default_license = EXCLUDED.default_license,"
        "   notes = EXCLUDED.notes"
        " RETURNING id",
        (
            SOURCE_NAME,
            SOURCE_NAME_NE,
            SOURCE_URL,
            DATASET_LICENSE,
            "Nepal's constitutional election authority — a first-party source for "
            "election results, independent of any ministry ('ministry' is merely the "
            "closest type this schema allows). Results portal: result.election.gov.np.",
        ),
    )
    source_id = _scalar(cur)
    cur.execute(
        "INSERT INTO datasets (source_id, name_en, license, update_frequency,"
        "  access_method, documentation_url)"
        " VALUES (%s, %s, %s, %s, 'api', %s)"
        " ON CONFLICT (source_id, name_en) DO UPDATE SET license = EXCLUDED.license,"
        "   update_frequency = EXCLUDED.update_frequency,"
        "   documentation_url = EXCLUDED.documentation_url"
        " RETURNING id",
        (
            source_id,
            DATASET_NAME,
            DATASET_LICENSE,
            "once per general election; no refresh between elections",
            DATASET_URL,
        ),
    )
    return int(_scalar(cur))


def seed_indicators(cur: psycopg.Cursor[Any], source_id: int, units: dict[str, int]) -> int:
    with SEED_CSV.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        unit_id = units.get(r["unit"])
        if unit_id is None:
            raise EcnLoadError(
                f"{r['code']}: unit {r['unit']!r} is not seeded — run `make seed` "
                f"after adding it to db/seeds/units.csv."
            )
        cur.execute(
            "INSERT INTO indicators"
            " (code, name_en, definition_en, unit_id, topic, source_concept,"
            "  origin_source_id, preferred_source_id)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (code) DO UPDATE SET"
            "   name_en = EXCLUDED.name_en, definition_en = EXCLUDED.definition_en,"
            "   unit_id = EXCLUDED.unit_id, topic = EXCLUDED.topic,"
            "   source_concept = EXCLUDED.source_concept,"
            "   origin_source_id = EXCLUDED.origin_source_id,"
            "   preferred_source_id = EXCLUDED.preferred_source_id",
            (
                r["code"],
                r["name_en"],
                r["definition_en"],
                unit_id,
                r["topic"],
                r["source_concept"],
                source_id,
                source_id,
            ),
        )
    return len(rows)


def build_rows(
    facts: CycleFacts,
    period_id: int,
    geo_ids: dict[str, int],
    district_map: dict[int, str],
    indicator_ids: dict[str, int],
    unit_ids: dict[str, int],
) -> list[tuple[Any, ...]]:
    """One tuple per observation: (indicator, geography, period, value, unit, breakdowns)."""
    out: list[tuple[Any, ...]] = []
    votes_iid = indicator_ids[VOTES_INDICATOR]
    seats_iid = indicator_ids[SEATS_INDICATOR]
    national = geo_ids[NATIONAL_GEO]

    for party, votes in facts.pr_national.items():
        out.append(
            (
                votes_iid,
                national,
                period_id,
                Decimal(votes),
                unit_ids[VOTES_UNIT],
                json.dumps({"party": party}, ensure_ascii=False),
            )
        )

    for ecn_code, per_party in facts.pr_by_district.items():
        geo_code = district_map.get(ecn_code)
        if geo_code is None:
            # Report, never guess: an unmapped district would silently vanish.
            raise EcnLoadError(
                f"{facts.cycle}: ECN district code {ecn_code} is not in "
                f"{DISTRICT_CSV}. Add it by hand — do not let a district drop out."
            )
        gid = geo_ids.get(geo_code)
        if gid is None:
            raise EcnLoadError(f"geography {geo_code} is not seeded — run `make seed`.")
        for party, votes in per_party.items():
            out.append(
                (
                    votes_iid,
                    gid,
                    period_id,
                    Decimal(votes),
                    unit_ids[VOTES_UNIT],
                    json.dumps({"party": party}, ensure_ascii=False),
                )
            )

    for party, seats in facts.seats_fptp.items():
        out.append(
            (
                seats_iid,
                national,
                period_id,
                Decimal(seats),
                unit_ids[SEATS_UNIT],
                json.dumps({"party": party, "system": "fptp"}, ensure_ascii=False),
            )
        )

    return out


def load(cycles: tuple[str, ...], dry_run: bool, write_raw: bool) -> int:
    load_dotenv()
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        raise EcnLoadError("DATABASE_URL is not set")

    district_map = read_district_map()
    print(f"District map: {len(district_map)} ECN codes -> geography codes ({DISTRICT_CSV})")

    client = EcnClient()
    client.open_session()
    raw: list[tuple[str, bytes, str]] = []
    facts_by_cycle: dict[str, CycleFacts] = {}
    for cycle in cycles:
        if cycle not in ELECTIONS:
            raise EcnLoadError(
                f"election {cycle} BS has no verified polling date in ELECTIONS. "
                f"Add one only from an ECN document — never from a guess."
            )
        print(f"\nReading election {cycle} BS ...")
        facts = harvest(client, cycle, raw)
        check(facts)
        facts_by_cycle[cycle] = facts

    all_parties = {p for f in facts_by_cycle.values() for p in f.pr_national}
    all_parties |= {p for f in facts_by_cycle.values() for p in f.seats_fptp}

    # English names the Commission itself publishes, from its by-election feed.
    ecn_english: dict[str, str] = {}
    try:
        for block in client.fetch_json("JSONFiles/BIElection/VoteCountHORPA.txt"):
            for cand in block.get("Candidates", []):
                ne, en = cand.get("PoliticalPartyName"), cand.get("PoliticalPartyNameEng")
                if ne and en:
                    ecn_english[ne] = en
    except EcnError as exc:
        print(f"  (no ECN-published English party names this run: {exc})")
    write_party_reference(all_parties, ecn_english)

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        clear_stale_pipeline_sessions(conn)
        cur.execute("SELECT code, id FROM units WHERE code = ANY(%s)", ([VOTES_UNIT, SEATS_UNIT],))
        unit_ids = {c: i for c, i in cur.fetchall()}
        for code in (VOTES_UNIT, SEATS_UNIT):
            if code not in unit_ids:
                raise EcnLoadError(
                    f"unit {code} is not seeded — run `make seed` (db/seeds/units.csv)."
                )

        dataset_id = ensure_source_and_dataset(cur)
        cur.execute("SELECT source_id FROM datasets WHERE id = %s", (dataset_id,))
        source_id = int(_scalar(cur))
        print(f"\nIndicators seeded/updated: {seed_indicators(cur, source_id, unit_ids)}")

        cur.execute(
            "SELECT code, id FROM indicators WHERE code = ANY(%s)",
            ([VOTES_INDICATOR, SEATS_INDICATOR],),
        )
        indicator_ids = {c: i for c, i in cur.fetchall()}

        wanted_geo = {NATIONAL_GEO} | set(district_map.values())
        cur.execute("SELECT code, id FROM geographies WHERE code = ANY(%s)", (sorted(wanted_geo),))
        geo_ids = {c: i for c, i in cur.fetchall()}
        missing_geo = wanted_geo - set(geo_ids)
        if missing_geo:
            raise EcnLoadError(
                f"{len(missing_geo)} geographies are not seeded: {sorted(missing_geo)[:5]}"
            )

        to_insert: list[tuple[Any, ...]] = []
        for cycle, facts in facts_by_cycle.items():
            year, poll_date, poll_bs = ELECTIONS[cycle]
            cur.execute(
                "SELECT id FROM time_periods WHERE period_type = 'year' AND gregorian_label = %s",
                (year,),
            )
            period_id = _scalar(cur)
            if period_id is None:
                raise EcnLoadError(f"no calendar-year period for {year} — run `make seed`.")
            print(f"  {cycle} BS: polled {poll_date} ({poll_bs} BS) -> calendar year {year}")
            to_insert.extend(
                build_rows(facts, period_id, geo_ids, district_map, indicator_ids, unit_ids)
            )

        # Skip cells already carrying the same value, so a re-run writes nothing.
        cur.execute(
            "SELECT indicator_id, geography_id, time_period_id, breakdowns, value"
            " FROM observations WHERE dataset_id = %s AND is_latest",
            (dataset_id,),
        )
        latest = {
            (iid, gid, pid, json.dumps(bd, ensure_ascii=False, sort_keys=True)): val
            for iid, gid, pid, bd, val in cur.fetchall()
        }
        fresh = []
        unchanged = 0
        for row in to_insert:
            iid, gid, pid, value, _unit, breakdowns = row
            key = (
                iid,
                gid,
                pid,
                json.dumps(json.loads(breakdowns), ensure_ascii=False, sort_keys=True),
            )
            if latest.get(key) == value:
                unchanged += 1
                continue
            fresh.append(row)

        print(f"\nObservations built: {len(to_insert):,}")
        print(f"  already loaded and unchanged: {unchanged:,}")
        print(f"  to write: {len(fresh):,}")

        if dry_run:
            print("\nDRY RUN — nothing written.")
            conn.rollback()
            return 0

        if write_raw and raw:
            try:
                lake = RawLake.from_env()
                stored = lake.store_snapshot(DATASET_CODE, raw, snapshot_filename="load.json")
                print(f"Raw archived: {stored.payload_path} ({stored.size_bytes:,} bytes)")
            except RawLakeError as exc:
                raise EcnLoadError(f"raw archive failed, so nothing was loaded: {exc}") from exc

        if not fresh:
            print("Nothing to load; the warehouse already matches the source.")
            return 0

        cur.execute(
            "INSERT INTO releases (dataset_id, release_date)"
            " VALUES (%s, CURRENT_DATE) RETURNING id",
            (dataset_id,),
        )
        release_id = _scalar(cur)
        for start in range(0, len(fresh), BATCH):
            chunk = fresh[start : start + BATCH]
            cur.executemany(
                "INSERT INTO observations"
                " (indicator_id, geography_id, time_period_id, dataset_id, release_id,"
                "  value, unit_id, breakdowns, status)"
                " VALUES (%s, %s, %s, "
                + str(dataset_id)
                + ", "
                + str(release_id)
                + ", %s, %s, %s, 'final')",
                chunk,
            )
            conn.commit()
            print(f"  committed {min(start + BATCH, len(fresh)):>6,} / {len(fresh):,}")
        print(f"\nLoaded {len(fresh):,} observations under release {release_id}.")
        return len(fresh)


def main(argv: list[str] | None = None) -> int:
    configure_stdout_utf8()
    parser = argparse.ArgumentParser(description="ECN.S3 — load election votes and seats.")
    parser.add_argument("--dry-run", action="store_true", help="write nothing")
    parser.add_argument("--no-raw", action="store_true", help="skip the raw-lake archive")
    parser.add_argument("--cycle", action="append", help="limit to one election (repeatable)")
    args = parser.parse_args(argv)

    cycles = tuple(args.cycle) if args.cycle else tuple(ELECTIONS)
    print("ECN.S3 — loading House of Representatives election results")
    print("=" * 62)
    load(cycles, dry_run=args.dry_run, write_raw=not args.no_raw)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (EcnLoadError, EcnError) as exc:
        print(f"\nLOAD FAILED: {exc}", file=sys.stderr)
        sys.exit(2)
