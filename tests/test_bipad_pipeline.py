"""BIPAD incident parsing and placement (DIS.S2). Offline: no DB, no network.

The fixtures are real BIPAD records, trimmed — a flood in Sindhupalchok and a
fire in Banke, both fetched 2026-09-07.
"""

from __future__ import annotations

from datetime import date

import pytest

from ingestion.bipad.client import point_of
from ingestion.bipad.pipeline import parse, place, slugify
from ingestion.common.geo_point import BoundaryIndex

# Jalbire, Jugal Rural Municipality-2, Sindhupalchok — a real record.
FLOOD = {
    "id": 93871,
    "title": "Flood at Jalbire, Jugal Rural Municipality-2",
    "titleNe": "बाग्मती, सिन्धुपाल्चोक, जुगल-२ मा बाढी",
    "wards": [2899],
    "point": {"type": "Point", "coordinates": [85.75568, 27.90711]},
    "incidentOn": "2026-08-31T00:00:00+05:45",
    "reportedOn": "2026-08-31T19:20:27+05:45",
    "streetAddress": "Jalbire",
    "verified": True,
    "hazard": 11,
    "loss": {
        "peopleDeathCount": 2,
        "peopleMissingCount": 0,
        "peopleInjuredCount": None,
        "peopleAffectedCount": 12,
        "familyAffectedCount": 3,
        "infrastructureDestroyedHouseCount": 1,
        "estimatedLoss": 150000,
    },
}

# Rapti Sonari Rural Municipality-2, Banke.
FIRE = {
    "id": 64504,
    "title": "Fire at Ram Gaau, Rapti Sonari Rural Municipality-2",
    "wards": [2164],
    "point": {"type": "Point", "coordinates": [81.84765, 28.09534]},
    "incidentOn": "2023-06-02T00:00:00+05:45",
    "verified": True,
    "hazard": 10,
    "loss": 211946,  # NOT expanded — BIPAD returns the loss id when ?expand is absent
}

HAZARDS = {10: "fire", 11: "flood", 17: "landslide"}


@pytest.fixture(scope="module")
def boundaries() -> dict[str, BoundaryIndex]:
    return {
        level: BoundaryIndex.for_level(level)
        for level in ("local_unit", "district", "province")
    }


def _parse(records, boundaries, wards=None, crosswalk=None):
    """(rows, rejections, examples) — the placement tally is checked separately."""
    rows, _how, rejected, examples = parse(
        records, HAZARDS, boundaries, wards or {}, crosswalk or {}
    )
    return rows, rejected, examples


# --- slugify ------------------------------------------------------------------


def test_a_hazard_code_is_a_stable_slug() -> None:
    assert slugify("Forest Fire") == "forest_fire"
    assert slugify("Glacial lake outburst") == "glacial_lake_outburst"
    assert slugify("Other (Natural)") == "other_natural"
    assert slugify("Leakage (toxic gas)") == "leakage_toxic_gas"


# --- placing ------------------------------------------------------------------


def test_an_incident_is_placed_by_its_own_coordinates(boundaries) -> None:
    """The point beats every name: it is where the source says it happened."""
    code, lat, lon, how = place(FLOOD, boundaries, {}, {})
    assert code is not None and code.startswith("NP03")  # Bagmati province
    assert (lat, lon) == (27.90711, 85.75568)
    assert how == "point (local_unit)"


def test_a_point_outside_nepal_falls_back_to_the_ward(boundaries) -> None:
    """A coordinate over the border is kept — it is what was published — but it
    cannot decide the district, so the ward does."""
    stray = {**FLOOD, "point": {"type": "Point", "coordinates": [85.1376, 25.5941]}}
    code, lat, lon, how = place(stray, boundaries, {2899: 500}, {500: "NP0323003"})
    assert code == "NP0323003"
    assert (lat, lon) == (25.5941, 85.1376)
    assert "ward" in how


def test_an_incident_with_no_point_is_placed_by_its_ward(boundaries) -> None:
    pointless = {k: v for k, v in FLOOD.items() if k != "point"}
    code, lat, lon, how = place(pointless, boundaries, {2899: 500}, {500: "NP0323003"})
    assert (code, lat, lon, how) == ("NP0323003", None, None, "ward")


def test_an_incident_that_cannot_be_placed_is_not_guessed(boundaries) -> None:
    """No point, and a ward nobody has mapped. The honest answer is 'nowhere'."""
    pointless = {k: v for k, v in FLOOD.items() if k != "point"}
    assert place(pointless, boundaries, {}, {})[0] is None


# --- parsing ------------------------------------------------------------------


def test_a_real_incident_parses_into_the_row_we_store(boundaries) -> None:
    placed, rejected, _ = _parse([FLOOD], boundaries)
    assert not rejected
    row = placed[0]
    assert row.source_incident_id == "93871"
    assert row.hazard_code == "flood"
    assert row.incident_on == date(2026, 8, 31)
    assert row.reported_on == date(2026, 8, 31)
    assert row.deaths == 2
    assert row.affected_families == 3
    assert row.houses_destroyed == 1
    assert row.estimated_loss_npr == 150000
    assert row.title_ne is not None and "बाढी" in row.title_ne
    assert row.verified is True


def test_a_published_zero_and_an_unpublished_figure_stay_different(boundaries) -> None:
    """`missing: 0` means the source counted none. `injured: null` means it did
    not say. Flattening one into the other would invent a fact."""
    row = _parse([FLOOD], boundaries)[0][0]
    assert row.missing == 0
    assert row.injured is None


def test_an_unexpanded_loss_id_is_not_mistaken_for_a_loss(boundaries) -> None:
    """Without ?expand=loss BIPAD sends the loss's id — an integer where a
    record belongs. Reading 211946 as a death toll would be a catastrophe."""
    row = _parse([FIRE], boundaries)[0][0]
    assert row.deaths is None
    assert row.estimated_loss_npr is None


def test_an_unknown_hazard_is_rejected_and_counted(boundaries) -> None:
    """BIPAD can add a hazard at any time. A record we cannot label is refused
    loudly, never filed under 'other'."""
    strange = {**FLOOD, "hazard": 999}
    placed, rejected, examples = _parse([strange], boundaries)
    assert placed == []
    assert rejected == {"unknown hazard": 1}
    assert "999" not in examples[0] and "93871" in examples[0]


def test_an_incident_with_no_date_is_rejected(boundaries) -> None:
    undated = {**FLOOD, "incidentOn": None}
    placed, rejected, _ = _parse([undated], boundaries)
    assert placed == []
    assert rejected == {"no usable date": 1}


def test_every_rejection_is_counted_by_reason(boundaries) -> None:
    """A pipeline that drops records silently is how bad data becomes invisible."""
    records = [
        FLOOD,
        {**FLOOD, "id": 2, "hazard": 999},
        {**FLOOD, "id": 3, "incidentOn": ""},
        {k: v for k, v in FLOOD.items() if k != "point"} | {"id": 4, "wards": []},
    ]
    placed, rejected, _ = _parse(records, boundaries)
    assert len(placed) == 1
    assert rejected == {
        "unknown hazard": 1,
        "no usable date": 1,
        "could not be placed": 1,
    }


# --- the client's point reader ------------------------------------------------


def test_point_of_reads_a_geojson_point() -> None:
    assert point_of(FLOOD) == (85.75568, 27.90711)


def test_point_of_returns_none_rather_than_a_default() -> None:
    """(0, 0) is a place in the Atlantic. An incident without a location must
    read as having none."""
    assert point_of({}) is None
    assert point_of({"point": None}) is None
    assert point_of({"point": {"type": "Polygon", "coordinates": [[1, 2]]}}) is None
    assert point_of({"point": {"type": "Point", "coordinates": [1]}}) is None


def test_a_national_park_is_placed_at_its_district_not_rejected(boundaries) -> None:
    """Nepal's national parks lie outside every local unit, so a snake bite in
    Shuklaphanta has a good coordinate belonging to no municipality. Recording
    it at Kanchanpur district keeps a real record at the precision the source
    supports; rejecting it would lose it, and snapping it to the nearest
    municipality would invent a place. Coordinates from BIPAD incident 92456."""
    snake_bite = {
        **FLOOD,
        "id": 92456,
        "title": "Snake Bite at Shuklaphanta National Park-99",
        "wards": [],
        "point": {"type": "Point", "coordinates": [80.31147, 28.84298]},
    }
    code, lat, lon, how = place(snake_bite, boundaries, {}, {})
    assert code == "NP0772"  # Kanchanpur district
    assert (lat, lon) == (28.84298, 80.31147)
    assert how == "point (district)"


# --- archiving ----------------------------------------------------------------


def test_the_archive_is_split_by_bytes_not_by_page_count() -> None:
    """Supabase refuses an object over 50 MB, and a full harvest is ~90 MB. A
    fixed page count would still overflow on a day of long records, so the
    split follows the actual bytes."""
    from ingestion.bipad.pipeline import chunk_pages

    pages = [(f"p{i}.json", b"x" * 400, "url") for i in range(10)]
    chunks = chunk_pages(pages, budget=1000)
    # Two pages fit in 1000 bytes; a third would not.
    assert [len(c) for c in chunks] == [2, 2, 2, 2, 2]
    assert sum(len(c) for c in chunks) == 10
    assert all(sum(len(p[1]) for p in c) <= 1000 for c in chunks)


def test_a_single_page_over_budget_is_still_archived_alone() -> None:
    """Refusing to store an oversized page would mean parsing bytes we never
    archived, which breaks raw-first. One part per page is the fallback."""
    from ingestion.bipad.pipeline import chunk_pages

    pages = [("big.json", b"x" * 5000, "url"), ("small.json", b"x", "url")]
    chunks = chunk_pages(pages, budget=1000)
    assert [len(c) for c in chunks] == [1, 1]


def test_no_pages_means_no_archive_parts() -> None:
    from ingestion.bipad.pipeline import chunk_pages

    assert chunk_pages([], budget=1000) == []


# --- the harvest must be whole ------------------------------------------------


def test_a_harvest_with_repeats_is_refused() -> None:
    """Duplicates are the fingerprint of unstable offset paging, which drops as
    many records as it repeats. The first full run hit exactly this: 63,151
    records carrying 62,729 distinct ids, because `ordering=incident_on` has no
    tie-break and thousands of incidents share a date."""
    from ingestion.bipad.pipeline import BipadPipelineError, check_harvest_is_whole

    with pytest.raises(BipadPipelineError, match="repeats"):
        check_harvest_is_whole([{"id": 1}, {"id": 2}, {"id": 1}])


def test_a_clean_harvest_passes() -> None:
    from ingestion.bipad.pipeline import check_harvest_is_whole

    assert check_harvest_is_whole([{"id": 1}, {"id": 2}, {"id": 3}]) == 0


def test_the_harvest_orders_by_a_unique_key() -> None:
    """Offset paging is only correct over a TOTAL ordering. `id` is unique;
    `incident_on` is not, and using it cost 422 records."""
    import inspect

    from ingestion.bipad.pipeline import harvest

    source = inspect.getsource(harvest)
    assert '"ordering": "id"' in source
