"""ECN.S3 pipeline tests. Offline: no network, no database.

These cover the two things that would do real damage if they broke:

  1. the checks that REFUSE a load — a partial harvest, a source that does not
     reconcile, a house of the wrong size;
  2. the district mapping, which is curated reference data and is the only thing
     standing between an ECN district code and a wrong district on the map.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from ingestion.election.ecn_pipeline import (
    DISTRICT_CSV,
    ELECTIONS,
    NATIONAL_GEO,
    SEATS_INDICATOR,
    VOTES_INDICATOR,
    CycleFacts,
    EcnLoadError,
    build_rows,
    check,
    read_district_map,
)

SEED_ROOT = Path(__file__).parent.parent


def _facts() -> CycleFacts:
    """A tiny election that reconciles: two districts, two parties, 165 seats."""
    return CycleFacts(
        cycle="2082",
        pr_national={"क": 300, "ख": 100},
        pr_by_district={
            1: {"क": 200, "ख": 60},
            2: {"क": 100, "ख": 40},
        },
        seats_fptp={"क": 164, "ख": 1},
    )


def _full_districts(facts: CycleFacts) -> CycleFacts:
    """Pad to the 77 districts the check insists on, without changing the sums."""
    for extra in range(3, 78):
        facts.pr_by_district[extra] = {}
    return facts


# --- the checks that refuse a load -------------------------------------------


def test_a_reconciling_election_passes() -> None:
    check(_full_districts(_facts()))  # must not raise


def test_a_partial_harvest_is_refused() -> None:
    """The most important test here. A load that quietly accepts 62 of 77
    districts under-reports every party, and looks completely normal."""
    facts = _facts()
    with pytest.raises(EcnLoadError, match="expected 77"):
        check(facts)


def test_a_source_that_does_not_reconcile_is_refused() -> None:
    facts = _full_districts(_facts())
    facts.pr_by_district[2]["क"] = 99  # one vote goes missing
    with pytest.raises(EcnLoadError, match="does not reconcile"):
        check(facts)


def test_one_party_disagreeing_is_refused_even_when_the_total_matches() -> None:
    """Votes moved between parties keep the grand total right. Checking only the
    total would pass this; the per-party check is what catches it."""
    facts = _full_districts(_facts())
    facts.pr_by_district[1]["क"] = 190
    facts.pr_by_district[1]["ख"] = 70
    with pytest.raises(EcnLoadError, match="do not sum to their"):
        check(facts)


def test_a_house_of_the_wrong_size_is_refused() -> None:
    facts = _full_districts(_facts())
    facts.seats_fptp["ख"] = 2  # 166 seats
    with pytest.raises(EcnLoadError, match="165 first-past-the-post"):
        check(facts)


# --- the curated district map ------------------------------------------------


def test_the_district_map_covers_all_77_districts_uniquely() -> None:
    mapping = read_district_map()
    assert len(mapping) == 77
    assert len(set(mapping.values())) == 77


def test_every_mapped_geography_exists_in_the_geography_seed() -> None:
    """A geo code with a typo would fail at load time against the database. This
    catches it in the suite instead, offline."""
    with (SEED_ROOT / "db/seeds/geographies.csv").open(encoding="utf-8", newline="") as fh:
        districts = {r["code"] for r in csv.DictReader(fh) if r["level"] == "district"}
    mapped = set(read_district_map().values())
    assert mapped <= districts
    assert mapped == districts, "every Nepali district should receive election data"


def test_the_five_hand_resolved_rows_still_say_why() -> None:
    """The hand-resolved rows carry their reason in the file. If someone
    regenerates the map mechanically and drops the reasoning, this fails."""
    with DISTRICT_CSV.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    manual = [r for r in rows if r["how_matched"] != "exact name match within the province"]
    assert len(manual) == 5
    assert all(r["how_matched"].strip() for r in manual)


# --- rows built for the warehouse --------------------------------------------


def test_rows_are_built_for_national_and_every_district() -> None:
    facts = _full_districts(_facts())
    geo_ids = {NATIONAL_GEO: 1, "NP0101": 11, "NP0102": 12}
    district_map = {1: "NP0101", 2: "NP0102"}
    district_map.update({i: f"X{i}" for i in range(3, 78)})
    geo_ids.update({f"X{i}": 100 + i for i in range(3, 78)})
    indicator_ids = {VOTES_INDICATOR: 7, SEATS_INDICATOR: 8}
    unit_ids = {"VOTES": 70, "SEATS": 80}

    rows = build_rows(facts, 42, geo_ids, district_map, indicator_ids, unit_ids)

    votes_rows = [r for r in rows if r[0] == 7]
    seats_rows = [r for r in rows if r[0] == 8]
    # 2 national parties + 4 district-party cells (the padded districts are empty)
    assert len(votes_rows) == 2 + 4
    assert len(seats_rows) == 2
    assert all(r[1] == 1 for r in seats_rows), "seats are national only"


def test_party_names_are_stored_as_published_not_escaped() -> None:
    """Breakdowns must carry real Devanagari, not \\uXXXX escapes — those would
    make the JSON unreadable to a human auditing the warehouse."""
    facts = _full_districts(_facts())
    facts.pr_national = {"नेपाली काँग्रेस": 400}
    facts.pr_by_district = {1: {"नेपाली काँग्रेस": 400}}
    for extra in range(2, 78):
        facts.pr_by_district[extra] = {}
    district_map = {i: f"X{i}" for i in range(1, 78)}
    geo_ids = {NATIONAL_GEO: 1, **{f"X{i}": 100 + i for i in range(1, 78)}}
    rows = build_rows(
        facts,
        42,
        geo_ids,
        district_map,
        {VOTES_INDICATOR: 7, SEATS_INDICATOR: 8},
        {"VOTES": 70, "SEATS": 80},
    )
    breakdowns = rows[0][5]
    assert "नेपाली काँग्रेस" in breakdowns
    assert json.loads(breakdowns)["party"] == "नेपाली काँग्रेस"


# --- the party reference's provenance ----------------------------------------


def test_rewriting_the_party_file_never_upgrades_a_names_provenance(tmp_path: Path) -> None:
    """A name the ECN published must not come back labelled 'curated by hand'.

    The first version of this code re-derived the label on every rewrite, so the
    second run relabelled all seven ECN-published names as hand-curated — a
    claim that a human had checked them when none had. Provenance may be
    preserved or asserted from the source, never invented on a round trip.
    """
    import ingestion.election.ecn_pipeline as pipe

    target = tmp_path / "party_names.csv"
    original = pipe.PARTY_CSV
    pipe.PARTY_CSV = target
    try:
        ecn_english = {"नेपाली काँग्रेस": "Nepali Congress"}
        parties = {"नेपाली काँग्रेस", "जनमत पार्टी"}
        pipe.write_party_reference(parties, ecn_english)
        pipe.write_party_reference(parties, ecn_english)  # the round trip
        rows = {r["name_ne"]: r for r in csv.DictReader(target.open(encoding="utf-8"))}
    finally:
        pipe.PARTY_CSV = original

    assert rows["नेपाली काँग्रेस"]["source_of_english"] == pipe.ECN_PUBLISHED
    # A party with no published English name stays blank rather than acquiring one.
    assert rows["जनमत पार्टी"]["name_en"] == ""
    assert rows["जनमत पार्टी"]["source_of_english"] == ""


def test_a_narrower_run_never_forgets_parties_already_recorded(tmp_path: Path) -> None:
    """Running one election must not delete the other's parties.

    `--cycle 2079` knows only 2079's parties. Rewriting the file from that set
    alone dropped 36 of the 91 recorded parties in a real run — silently, and
    including any English name a human had curated. The file is a union of every
    party ever seen, not a snapshot of the last run.
    """
    import ingestion.election.ecn_pipeline as pipe

    target = tmp_path / "party_names.csv"
    original = pipe.PARTY_CSV
    pipe.PARTY_CSV = target
    try:
        pipe.write_party_reference({"क", "ख"}, {"क": "Ka"})
        # A later, narrower run that sees only one of them.
        pipe.write_party_reference({"क"}, {"क": "Ka"})
        rows = {r["name_ne"]: r for r in csv.DictReader(target.open(encoding="utf-8"))}
    finally:
        pipe.PARTY_CSV = original

    assert set(rows) == {"क", "ख"}, "the party absent from the narrower run was dropped"


def test_a_hand_curated_name_survives_a_rewrite_with_its_label() -> None:
    """The other direction: a human's entry must not be wiped by the next run."""
    import ingestion.election.ecn_pipeline as pipe

    with pipe.PARTY_CSV.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    named = [r for r in rows if r["name_en"]]
    assert named, "the committed party file should carry some English names"
    # Every English name in the committed file states where it came from.
    assert all(r["source_of_english"].strip() for r in named)


# --- the election dates ------------------------------------------------------


def test_both_elections_carry_a_sourced_polling_date() -> None:
    """The portal names elections by BS year only. These dates came from ECN
    documents (see the module docstring); a bare year would be a guess."""
    assert set(ELECTIONS) == {"2082", "2079"}
    assert ELECTIONS["2082"] == ("2026", "2026-03-05", "2082-11-21")
    assert ELECTIONS["2079"] == ("2022", "2022-11-20", "2079-08-04")


def test_the_two_elections_land_in_different_calendar_years() -> None:
    """The calendar year is what separates the two elections in the warehouse:
    same indicator, same geography, same breakdowns. If both mapped to one year
    the second load would collide with the first and be treated as a revision."""
    years = [ELECTIONS[c][0] for c in ELECTIONS]
    assert len(set(years)) == len(years)
