"""Offline tests for the Hhld05 floor-material Shape-A configuration."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from ingestion.nso.census_floor_material import CATEGORY_COLUMNS
from ingestion.nso.census_shape_a import GeographyMaps, parse_source

HEADER = (
    "prov,dist,gapa,provname,dname,gapaname,rowtotal,"
    + ",".join(CATEGORY_COLUMNS)
    + "\n"
)


def _row(prov: int, dist: int, gapa: int, total: int, categories: list[int]) -> str:
    return (
        f"{prov},{dist},{gapa},P{prov},D{dist},G{gapa},{total},"
        + ",".join(str(value) for value in categories)
        + "\n"
    )


def test_floor_parser_maps_all_levels_and_preserves_source_codes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "Hhld05.csv"
    source.write_text(
        HEADER
        + _row(0, 0, 0, 10, [1, 1, 1, 1, 1, 5])
        + _row(1, 0, 0, 10, [1, 1, 1, 1, 1, 5])
        + _row(1, 1, 0, 10, [1, 1, 1, 1, 1, 5])
        + _row(1, 1, 1, 10, [1, 1, 1, 1, 1, 5]),
        encoding="utf-8",
    )
    maps = GeographyMaps(
        provinces={"1": "NP01"},
        districts={"1": "NP0101"},
        local_units={("1", "1"): "NP0101301"},
    )

    values, failures, levels, skipped = parse_source(
        source,
        maps,
        CATEGORY_COLUMNS,
    )

    assert failures == []
    assert skipped == 0
    assert levels == {"country": 1, "province": 1, "district": 1, "local_unit": 1}
    assert len(values) == 28
    national = [value for value in values if value.geography_code == "NP"]
    assert national[0].breakdowns == {}
    assert national[0].value == Decimal("10")
    assert [value.breakdowns["category"] for value in national[1:]] == list(
        CATEGORY_COLUMNS
    )


def test_floor_parser_rejects_bad_category_sum(tmp_path: Path) -> None:
    source = tmp_path / "Hhld05.csv"
    source.write_text(
        HEADER + _row(1, 1, 1, 10, [1, 1, 1, 1, 1, 1]),
        encoding="utf-8",
    )
    maps = GeographyMaps(
        provinces={"1": "NP01"},
        districts={"1": "NP0101"},
        local_units={("1", "1"): "NP0101301"},
    )

    values, failures, levels, skipped = parse_source(
        source,
        maps,
        CATEGORY_COLUMNS,
    )

    assert values == []
    assert levels == {}
    assert skipped == 0
    assert len(failures) == 1
    assert "categories sum to 6, not rowtotal 10" in failures[0]
