"""Point-in-boundary lookup (DIS.S1).

Runs offline against hand-built shapes for the geometry itself, and against the
repository's real boundary files for the facts that matter operationally —
753 local units, and Kathmandu being where Kathmandu is.
"""

from __future__ import annotations

import json

import pytest

from ingestion.common.geo_point import Boundary, BoundaryIndex, _in_ring

# A unit square and a square with a hole, in lon/lat order.
SQUARE = [[0.0, 0.0], [0.0, 10.0], [10.0, 10.0], [10.0, 0.0], [0.0, 0.0]]
HOLE = [[4.0, 4.0], [4.0, 6.0], [6.0, 6.0], [6.0, 4.0], [4.0, 4.0]]


def _index(features: list[dict]) -> BoundaryIndex:
    boundaries = []
    for feature in features:
        rings = tuple(feature["rings"])
        lons = [p[0] for p in rings[0]]
        lats = [p[1] for p in rings[0]]
        boundaries.append(
            Boundary(
                code=feature["code"],
                min_lon=min(lons),
                min_lat=min(lats),
                max_lon=max(lons),
                max_lat=max(lats),
                polygons=(rings,),
            )
        )
    return BoundaryIndex(boundaries)


def test_a_point_inside_a_simple_shape_is_found() -> None:
    index = _index([{"code": "A", "rings": [SQUARE]}])
    assert index.locate(5.0, 5.0) == "A"


def test_a_point_outside_every_shape_is_None_not_the_nearest() -> None:
    """The whole reason this module exists: a near miss must not be reported as
    a hit. An incident 40 km outside a district belongs to no district here."""
    index = _index([{"code": "A", "rings": [SQUARE]}])
    assert index.locate(20.0, 5.0) is None
    assert index.locate(-1.0, -1.0) is None


def test_a_hole_is_not_inside() -> None:
    index = _index([{"code": "A", "rings": [SQUARE, HOLE]}])
    assert index.locate(1.0, 1.0) == "A"
    assert index.locate(5.0, 5.0) is None


def test_the_placeholder_zero_coordinate_lands_nowhere() -> None:
    """DesInventar writes latitude 0 for all 24,257 of its records. That must
    read as 'no location', never as a point off the coast of Africa matching
    something by accident."""
    index = BoundaryIndex.for_level("district")
    assert index.locate(0.0, 0.0) is None


def test_ray_casting_handles_a_ring_given_clockwise_or_anticlockwise() -> None:
    assert _in_ring(5.0, 5.0, SQUARE) is True
    assert _in_ring(5.0, 5.0, list(reversed(SQUARE))) is True


def test_an_unsupported_level_says_which_levels_exist() -> None:
    with pytest.raises(ValueError, match="ward"):
        BoundaryIndex.for_level("ward")


# --- against the repository's real boundary files ----------------------------


def test_every_level_loads_the_expected_number_of_boundaries() -> None:
    assert len(BoundaryIndex.for_level("province")) == 7
    assert len(BoundaryIndex.for_level("district")) == 77
    assert len(BoundaryIndex.for_level("local_unit")) == 753


@pytest.mark.parametrize(
    ("place", "lon", "lat", "level", "expected"),
    [
        # Kathmandu's centre: province Bagmati, district Kathmandu.
        ("Kathmandu", 85.324, 27.7172, "province", "NP03"),
        ("Kathmandu", 85.324, 27.7172, "district", "NP0327"),
        # Pokhara, Gandaki province.
        ("Pokhara", 83.9856, 28.2096, "province", "NP04"),
        # Biratnagar, Koshi province, Morang district.
        ("Biratnagar", 87.2718, 26.4525, "province", "NP01"),
    ],
)
def test_known_places_land_in_the_right_geography(
    place: str, lon: float, lat: float, level: str, expected: str
) -> None:
    assert BoundaryIndex.for_level(level).locate(lon, lat) == expected, place


def test_a_point_in_india_is_outside_every_nepali_district() -> None:
    # Patna, Bihar — well south of the border.
    assert BoundaryIndex.for_level("district").locate(85.1376, 25.5941) is None


def test_boundary_codes_match_the_seeded_geographies() -> None:
    """The map and the warehouse must name places identically, or a located
    incident cannot be filed against a geography row."""
    import csv
    from pathlib import Path

    seeds = Path(__file__).resolve().parent.parent / "db" / "seeds" / "geographies.csv"
    with seeds.open(encoding="utf-8") as fh:
        by_level: dict[str, set[str]] = {}
        for row in csv.DictReader(fh):
            by_level.setdefault(row["level"], set()).add(row["code"])
    for level in ("province", "district", "local_unit"):
        drawn = {b.code for b in BoundaryIndex.for_level(level).boundaries}
        assert drawn == by_level[level], f"{level}: boundary codes differ from the seeds"


def test_geojson_without_the_code_property_fails_loudly(tmp_path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "properties": {"NAME": "somewhere"},
                        "geometry": {"type": "Polygon", "coordinates": [SQUARE]},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="ADM3_PCODE"):
        BoundaryIndex.from_geojson(path, "ADM3_PCODE")
