"""Offline tests for the Shape-A Hhld06 census parser."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from ingestion.nso.census_drinking_water import (
    CATEGORY_COLUMNS,
    GeographyMaps,
    parse_source,
)

HEADER = (
    "prov,dist,gapa,provname,dname,gapaname,rowtotal," + ",".join(CATEGORY_COLUMNS) + "\n"
)


def _row(prov: int, dist: int, gapa: int, total: int, categories: list[int]) -> str:
    return (
        f"{prov},{dist},{gapa},P{prov},D{dist},G{gapa},{total},"
        + ",".join(str(value) for value in categories)
        + "\n"
    )


def test_parse_source_maps_every_level_and_preserves_raw_categories(tmp_path: Path) -> None:
    source = tmp_path / "Hhld06.csv"
    source.write_text(
        HEADER
        + _row(0, 0, 0, 10, [1, 1, 1, 1, 1, 1, 1, 1, 2])
        + _row(1, 0, 0, 10, [1, 1, 1, 1, 1, 1, 1, 1, 2])
        + _row(1, 1, 0, 10, [1, 1, 1, 1, 1, 1, 1, 1, 2])
        + _row(1, 1, 1, 10, [1, 1, 1, 1, 1, 1, 1, 1, 2]),
        encoding="utf-8",
    )
    maps = GeographyMaps(
        provinces={"1": "NP01"},
        districts={"1": "NP0101"},
        local_units={("1", "1"): "NP0101301"},
    )

    values, failures, levels, skipped = parse_source(source, maps)

    assert failures == []
    assert skipped == 0
    assert levels == {"country": 1, "province": 1, "district": 1, "local_unit": 1}
    assert len(values) == 40
    national = [value for value in values if value.geography_code == "NP"]
    assert national[0].breakdowns == {}
    assert national[0].value == Decimal("10")
    assert [value.breakdowns["category"] for value in national[1:]] == list(
        CATEGORY_COLUMNS
    )


def test_parse_source_reports_unmapped_geography_and_bad_sum(tmp_path: Path) -> None:
    source = tmp_path / "Hhld06.csv"
    source.write_text(
        HEADER
        + _row(1, 1, 1, 10, [1, 1, 1, 1, 1, 1, 1, 1, 1])
        + _row(1, 1, 2, 10, [1, 1, 1, 1, 1, 1, 1, 1, 2]),
        encoding="utf-8",
    )
    maps = GeographyMaps(
        provinces={"1": "NP01"},
        districts={"1": "NP0101"},
        local_units={("1", "1"): "NP0101301"},
    )

    values, failures, levels, skipped = parse_source(source, maps)

    assert values == []
    assert levels == {}
    assert skipped == 0
    assert any("categories sum" in failure for failure in failures)
    assert any("unmapped" in failure for failure in failures)


def test_parse_source_skips_institutional_and_reports_duplicate(tmp_path: Path) -> None:
    source = tmp_path / "Hhld06.csv"
    source.write_text(
        HEADER
        + _row(1, 1, 99, 10, [1, 1, 1, 1, 1, 1, 1, 1, 2])
        + _row(1, 1, 1, 10, [1, 1, 1, 1, 1, 1, 1, 1, 2])
        + _row(1, 1, 1, 10, [1, 1, 1, 1, 1, 1, 1, 1, 2]),
        encoding="utf-8",
    )
    maps = GeographyMaps(
        provinces={"1": "NP01"},
        districts={"1": "NP0101"},
        local_units={("1", "1"): "NP0101301"},
    )

    values, failures, levels, skipped = parse_source(source, maps)

    assert len(values) == 10
    assert levels == {"local_unit": 1}
    assert skipped == 1
    assert failures == [
        "line 4: duplicate geography NP0101301 (G1)",
    ]


def test_parse_source_rejects_unexpected_header(tmp_path: Path) -> None:
    source = tmp_path / "Hhld06.csv"
    source.write_text(HEADER.replace("i_Others", "i_Unknown"), encoding="utf-8")

    values, failures, levels, skipped = parse_source(
        source,
        GeographyMaps(provinces={}, districts={}, local_units={}),
    )

    assert values == []
    assert len(failures) == 1
    assert failures[0].startswith("unexpected columns:")
    assert levels == {}
    assert skipped == 0
