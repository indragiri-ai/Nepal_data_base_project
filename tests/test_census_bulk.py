"""Offline tests for manifest compilation and bulk census parsing."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from ingestion.nso.census_bulk import (
    BulkParseError,
    FileSpec,
    IndicatorSpec,
    ParseStats,
    SumRule,
    breakdown_key,
    iter_cells,
)
from ingestion.nso.census_shape_a import GeographyMaps
from scripts.census_bulk_manifest import _sum_rules_for, compile_file


def test_breakdown_key_is_independent_of_key_order() -> None:
    """The change check compares a stored mapping against a parsed one.

    Postgres returns jsonb keys in its own order (shortest first, then
    bytewise); the parser builds them in source-column order. If the two keys
    disagree, no stored cell is ever recognised and every re-run reloads the
    whole file, so both sides must normalise identically.
    """
    from_parser = {"agegrpname": "15 - 19 Years", "sexname": "Female"}
    from_postgres = {"sexname": "Female", "agegrpname": "15 - 19 Years"}

    assert breakdown_key(from_parser) == breakdown_key(from_postgres)
    assert breakdown_key({}) == "{}"


def test_hierarchical_tables_get_curated_sum_rules_not_the_flat_one() -> None:
    """Hhld10 is multiple-response: a household may own a radio AND a TV.

    A flat "every category sums to rowtotal" check rejects it (35.6M against
    6.66M households), which is why the file could not load. Only the
    no-facility/at-least-one split is a real identity.
    """
    measures = ["rowtotal", "x_NoFacility", "atleastOne", "a_Radio", "b_TV"]

    rules = _sum_rules_for("Hhld10_HouseholdFacility", measures)

    assert [r.total for r in rules] == ["rowtotal"]
    assert rules[0].parts == ["x_NoFacility", "atleastOne"]
    assert "a_Radio" not in rules[0].parts


def test_flat_tables_still_get_the_default_every_category_rule() -> None:
    rules = _sum_rules_for("Hhld07_TypeOfCookingFuel", ["rowtotal", "a_firewood", "b_LPGas"])

    assert len(rules) == 1
    assert rules[0].total == "rowtotal"
    assert rules[0].parts == ["a_firewood", "b_LPGas"]


def test_a_violated_sum_rule_blocks_the_file() -> None:
    """A source whose own arithmetic disagrees must fail loudly, not load."""
    payload = (
        b"prov,dist,gapa,provname,dname,gapaname,rowtotal,a_yes,b_no\n"
        b'0,0,0,"NEPAL","NEPAL","NEPAL",10,6,9\n'
    )
    spec = FileSpec(
        stem="Indv99_TestTable",
        source_csv=Path("unused.csv"),
        header_line=1,
        header=(
            "prov", "dist", "gapa", "provname", "dname", "gapaname",
            "rowtotal", "a_yes", "b_no",
        ),
        has_gapa=True,
        dimension_columns=(),
        split_dimensions=(),
        total_dimension_values={},
        label_columns=(),
        measure_columns=("rowtotal", "a_yes", "b_no"),
        sum_rules=(SumRule(total="rowtotal", parts=("a_yes", "b_no")),),
        row_count=1,
        indicator_specs=(
            IndicatorSpec(
                code="CENSUS_TEST_TOTAL", unit_code="PERSONS",
                measure="rowtotal", split_values={},
            ),
        ),
    )

    with pytest.raises(BulkParseError, match="15 != rowtotal 10"):
        list(iter_cells(payload, spec, GeographyMaps({}, {}, {}), "full", ParseStats()))


def test_manifest_compiler_discovers_published_total_code(tmp_path: Path) -> None:
    source = tmp_path / "Indv99_TestTable.csv"
    source.write_text(
        "title,,,,,,,,\n"
        "prov,dist,gapa,sex,provname,dname,gapaname,sexname,rowtotal,a_yes,b_no\n"
        '0,0,0,-1,"NEPAL","NEPAL","NEPAL","Total",10,6,4\n'
        '0,0,0,1,"NEPAL","NEPAL","NEPAL","Male",6,4,2\n',
        encoding="utf-8",
    )

    spec = compile_file(source)

    assert spec.header_line == 2
    assert spec.dimension_columns == ["sex"]
    assert spec.total_dimension_values == {"sex": "-1"}
    assert spec.split_dimensions == []
    assert spec.measure_columns == ["rowtotal", "a_yes", "b_no"]
    assert len(spec.indicator_specs) == 3


def test_bulk_parser_emits_headline_and_source_label_breakdown() -> None:
    payload = (
        b"prov,dist,gapa,sex,provname,dname,gapaname,sexname,rowtotal,a_yes,b_no\n"
        b'0,0,0,-1,"NEPAL","NEPAL","NEPAL","Total",10,6,4\n'
        b'0,0,0,1,"NEPAL","NEPAL","NEPAL","Male",6,4,2\n'
    )
    indicators = tuple(
        IndicatorSpec(
            code=f"CENSUS_TEST_{measure.upper()}",
            unit_code="PERSONS",
            measure=measure,
            split_values={},
        )
        for measure in ("rowtotal", "a_yes", "b_no")
    )
    spec = FileSpec(
        stem="Indv99_TestTable",
        source_csv=Path("unused.csv"),
        header_line=1,
        header=(
            "prov",
            "dist",
            "gapa",
            "sex",
            "provname",
            "dname",
            "gapaname",
            "sexname",
            "rowtotal",
            "a_yes",
            "b_no",
        ),
        has_gapa=True,
        dimension_columns=("sex",),
        split_dimensions=(),
        total_dimension_values={"sex": "-1"},
        label_columns=("sexname",),
        measure_columns=("rowtotal", "a_yes", "b_no"),
        sum_rules=(SumRule(total="rowtotal", parts=("a_yes", "b_no")),),
        row_count=2,
        indicator_specs=indicators,
    )
    maps = GeographyMaps(provinces={}, districts={}, local_units={})
    stats = ParseStats()

    cells = list(iter_cells(payload, spec, maps, "full", stats))

    assert len(cells) == 6
    assert cells[0].breakdowns == {}
    assert cells[0].value == Decimal("10")
    assert cells[3].breakdowns == {"sex": "Male"}
    assert cells[3].value == Decimal("6")


def test_balanced_mode_skips_only_local_detailed_cells() -> None:
    payload = (
        b"prov,dist,gapa,sex,provname,dname,gapaname,sexname,rowtotal\n"
        b'1,1,1,-1,"P","D","G","Total",10\n'
        b'1,1,1,1,"P","D","G","Male",6\n'
    )
    spec = FileSpec(
        stem="Indv99_TestTable",
        source_csv=Path("unused.csv"),
        header_line=1,
        header=(
            "prov",
            "dist",
            "gapa",
            "sex",
            "provname",
            "dname",
            "gapaname",
            "sexname",
            "rowtotal",
        ),
        has_gapa=True,
        dimension_columns=("sex",),
        split_dimensions=(),
        total_dimension_values={"sex": "-1"},
        label_columns=("sexname",),
        measure_columns=("rowtotal",),
        sum_rules=(),
        row_count=2,
        indicator_specs=(
            IndicatorSpec(
                code="CENSUS_TEST_TOTAL",
                unit_code="PERSONS",
                measure="rowtotal",
                split_values={},
            ),
        ),
    )
    maps = GeographyMaps(
        provinces={"1": "NP01"},
        districts={"1": "NP0101"},
        local_units={("1", "1"): "NP0101301"},
    )
    stats = ParseStats()

    cells = list(iter_cells(payload, spec, maps, "balanced", stats))

    assert len(cells) == 1
    assert cells[0].breakdowns == {}
    assert stats.mode_cells_skipped == 1
