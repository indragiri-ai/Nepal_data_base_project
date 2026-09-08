"""The disaster reference seeds (DIS.S1).

These files decide which place every disaster record is filed against, for 55
years of data. A wrong row here does not crash anything — it quietly moves a
flood to the wrong district — so the checks are about completeness and
agreement with the gazetteer, not about parsing.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

SEEDS = Path(__file__).resolve().parent.parent / "db" / "seeds"
REFERENCE = Path(__file__).resolve().parent.parent / "reference" / "bipad"

RESTRUCTURING_DATE = "2015-09-20"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def current() -> dict[str, list[dict[str, str]]]:
    by_level: dict[str, list[dict[str, str]]] = {}
    for row in _rows(SEEDS / "geographies.csv"):
        by_level.setdefault(row["level"], []).append(row)
    return by_level


@pytest.fixture(scope="module")
def old() -> list[dict[str, str]]:
    return _rows(SEEDS / "geographies_old.csv")


@pytest.fixture(scope="module")
def crosswalk() -> list[dict[str, str]]:
    return _rows(SEEDS / "geography_crosswalk.csv")


@pytest.fixture(scope="module")
def bipad() -> list[dict[str, str]]:
    return _rows(SEEDS / "bipad_geography_crosswalk.csv")


# --- the pre-2015 structure ---------------------------------------------------


def test_the_old_structure_is_five_regions_and_seventyfive_districts(
    old: list[dict[str, str]],
) -> None:
    """Nepal before 2015: 5 development regions, 75 districts. The list comes
    from Nepal's own DesInventar database, not from memory."""
    levels = [row["level"] for row in old]
    assert levels.count("old_region") == 5
    assert levels.count("old_district") == 75


def test_old_codes_cannot_collide_with_current_ones(
    old: list[dict[str, str]], current: dict[str, list[dict[str, str]]]
) -> None:
    """`geographies.code` is unique across every level, so an old district
    sharing a code with a current one would be unloadable."""
    old_codes = {row["code"] for row in old}
    current_codes = {row["code"] for rows in current.values() for row in rows}
    assert len(old_codes) == len(old)
    assert old_codes.isdisjoint(current_codes)


def test_every_old_district_sits_under_a_region_in_this_file(
    old: list[dict[str, str]],
) -> None:
    regions = {row["code"] for row in old if row["level"] == "old_region"}
    for row in old:
        if row["level"] == "old_district":
            assert row["parent_code"] in regions, row["code"]
        else:
            assert row["parent_code"] == "NP"


def test_the_old_structure_stops_at_the_restructuring(old: list[dict[str, str]]) -> None:
    """Validity dates are what stop a 1994 flood being served as though it
    happened under today's boundaries."""
    assert {row["valid_to"] for row in old} == {RESTRUCTURING_DATE}


def test_every_old_district_keeps_a_pointer_to_its_source_record(
    old: list[dict[str, str]],
) -> None:
    for row in old:
        if row["level"] == "old_district":
            assert row["geometry_ref"].startswith("DESINVENTAR_LEVEL1="), row["code"]


# --- the 2015 crosswalk -------------------------------------------------------


def test_the_crosswalk_covers_every_district_that_survived_unchanged(
    crosswalk: list[dict[str, str]], old: list[dict[str, str]]
) -> None:
    """73 of the 75 districts came through the restructuring with the same
    boundary. The other two were split."""
    assert len(crosswalk) == 73
    old_districts = {row["code"] for row in old if row["level"] == "old_district"}
    assert {row["old_code"] for row in crosswalk} <= old_districts


def test_the_two_split_districts_are_deliberately_absent(
    crosswalk: list[dict[str, str]], old: list[dict[str, str]]
) -> None:
    """Nawalparasi became East and West; Rukum likewise. Nobody has published a
    share that says how a 1998 flood there divides between them, so there is no
    row — the records stay at the old district and say so."""
    mapped = {row["old_code"] for row in crosswalk}
    unmapped = {
        row["name_en"]
        for row in old
        if row["level"] == "old_district" and row["code"] not in mapped
    }
    assert unmapped == {"Nawalparasi", "Rukum"}


def test_every_crosswalk_target_is_a_real_current_district(
    crosswalk: list[dict[str, str]], current: dict[str, list[dict[str, str]]]
) -> None:
    districts = {row["code"] for row in current["district"]}
    for row in crosswalk:
        assert row["new_code"] in districts, row["old_code"]


def test_no_district_is_claimed_by_two_old_districts(
    crosswalk: list[dict[str, str]],
) -> None:
    targets = [row["new_code"] for row in crosswalk]
    assert len(targets) == len(set(targets))


def test_an_unchanged_boundary_carries_the_whole_share(
    crosswalk: list[dict[str, str]],
) -> None:
    assert {row["allocation_share"] for row in crosswalk} == {"1.0"}


def test_a_renaming_is_recorded_as_reviewed_not_as_an_exact_match(
    crosswalk: list[dict[str, str]],
) -> None:
    """Six districts are romanised differently by the two sources — Kavre for
    Kabhrepalanchok, Mahotari for Mahottari. Those were settled by a person and
    must say so, so nobody later mistakes them for machine-verified."""
    reviewed = {row["old_name_en"] for row in crosswalk if row["method"] == "manual_review"}
    assert reviewed == {
        "Sindhupalchoke",
        "Kavre",
        "Makwanpur",
        "Dhanusa",
        "Mahotari",
        "Arghakanchi",
    }
    for row in crosswalk:
        assert row["method"] in {"exact_name", "manual_review"}


# --- the BIPAD crosswalk ------------------------------------------------------


def test_bipad_resolves_to_every_district_and_every_local_unit(
    bipad: list[dict[str, str]], current: dict[str, list[dict[str, str]]]
) -> None:
    """Not "most of them": all 77 districts and all 753 local units. A gap here
    is a district whose disasters would silently go unrecorded."""
    districts = {row["geography_code"] for row in bipad if row["bipad_level"] == "district"}
    local_units = {row["geography_code"] for row in bipad if row["bipad_level"] == "municipality"}
    assert districts == {row["code"] for row in current["district"]}
    assert local_units == {row["code"] for row in current["local_unit"]}


def test_no_bipad_place_is_listed_twice(bipad: list[dict[str, str]]) -> None:
    keys = [(row["bipad_level"], row["bipad_id"]) for row in bipad]
    assert len(keys) == len(set(keys))


def test_no_two_bipad_places_point_at_the_same_geography(
    bipad: list[dict[str, str]],
) -> None:
    for level in ("district", "municipality"):
        codes = [row["geography_code"] for row in bipad if row["bipad_level"] == level]
        assert len(codes) == len(set(codes)), level


def test_every_row_records_which_evidence_resolved_it(
    bipad: list[dict[str, str]],
) -> None:
    """'boundary' means the names differ and the coordinate decided it — 159 of
    them. Keeping the evidence is what lets a reader audit the mapping."""
    kinds = {row["evidence"] for row in bipad}
    assert kinds <= {"both", "name", "boundary", "manual_review"}
    assert "both" in kinds and "boundary" in kinds


def test_the_places_bipad_lists_that_are_not_local_units_are_all_explained() -> None:
    """BIPAD lists 774 municipalities where Nepal has 753. Every extra must have
    a stated reason, or something upstream has changed and a person should look."""
    unresolved = _rows(REFERENCE / "crosswalk_unresolved.csv")
    protected = [
        row
        for row in unresolved
        if row["reason"] == "not a local unit (protected or special area)"
    ]
    assert len(protected) == 21


def test_nothing_unresolved_is_a_contradiction() -> None:
    """A place where the name and the coordinate disagree is never written to
    the seed. If one ever appears, this fails and a person settles it."""
    unresolved = _rows(REFERENCE / "crosswalk_unresolved.csv")
    assert not [row for row in unresolved if "disagree" in row["reason"]]


def test_every_contested_place_was_settled_by_a_person(
    bipad: list[dict[str, str]],
) -> None:
    """When two places claimed one municipality the tool trusted neither. Each
    one must reappear in the seed through a reviewed override, with the
    reasoning written down — otherwise a municipality is left unmapped."""
    unresolved = _rows(REFERENCE / "crosswalk_unresolved.csv")
    contested = {
        (row["bipad_level"], row["bipad_id"])
        for row in unresolved
        if row["reason"] == "two places resolve to the same geography"
    }
    overrides = _rows(SEEDS / "bipad_geography_overrides.csv")
    settled = {(row["bipad_level"], row["bipad_id"]) for row in overrides}
    assert contested <= settled, contested - settled
    for row in overrides:
        assert row["reviewed_by"] and row["reviewed_on"] and len(row["reason"]) > 40
    seeded = {(row["bipad_level"], row["bipad_id"]) for row in bipad}
    assert contested <= seeded
