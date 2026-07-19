"""Census 2021 layout: parsers, registry/CSV sync, and quality-gate bands.

Fixtures are REAL NSO API payloads captured 2026-07-19 (see
reference/census/PROVENANCE.md); the expected numbers below are the published
Census 2021 national results, so a parser regression that changes any value
fails against ground truth, not against itself.
"""

from __future__ import annotations

import json
from csv import DictReader
from decimal import Decimal
from pathlib import Path

import pytest

from ingestion.common.quality import Candidate, run_quality_gate
from ingestion.nso.census_layout import (
    REGISTRY,
    CensusParseError,
    parse_highlight,
    parse_literacy,
)

FIXTURES = Path("tests/fixtures/census")


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_highlight_parses_published_national_figures() -> None:
    values = {(v.indicator_code, tuple(sorted(v.breakdowns.items()))): v.value
              for v in parse_highlight(_load("highlight_national.json"), "test")}
    assert values[("CENSUS_POP_TOTAL", ())] == Decimal("29164578")
    assert values[("CENSUS_POP_TOTAL", (("sex", "male"),))] == Decimal("14253551")
    assert values[("CENSUS_POP_TOTAL", (("sex", "female"),))] == Decimal("14911027")
    assert values[("CENSUS_SEX_RATIO", ())] == Decimal("95.59")
    assert values[("CENSUS_POP_DENSITY", ())] == Decimal("198")
    assert values[("CENSUS_POP_GROWTH", ())] == Decimal("0.92")


def test_literacy_parses_published_rates_by_sex() -> None:
    values = {tuple(sorted(v.breakdowns.items())): v.value
              for v in parse_literacy(_load("literacy_national.json"), "test")}
    assert values[()] == Decimal("76.2")
    assert values[(("sex", "male"),)] == Decimal("83.6")
    assert values[(("sex", "female"),)] == Decimal("69.4")


def test_missing_field_fails_loudly_never_guesses() -> None:
    payload = _load("highlight_national.json")
    del payload["data"]["sex_ratio"]
    with pytest.raises(CensusParseError, match="sex_ratio"):
        parse_highlight(payload, "test")


def test_unexpected_literacy_series_fails_loudly() -> None:
    payload = _load("literacy_national.json")
    payload["data"]["literacyBySex"]["series"][0]["name"] = "Unknown"
    with pytest.raises(CensusParseError):
        parse_literacy(payload, "test")


def test_registry_and_seed_csv_stay_in_sync() -> None:
    with Path("db/seeds/indicators_census.csv").open(encoding="utf-8", newline="") as fh:
        csv_rows = {r["code"]: r for r in DictReader(fh)}
    assert set(csv_rows) == {i.code for i in REGISTRY}
    for ind in REGISTRY:
        row = csv_rows[ind.code]
        assert row["name_en"] == ind.name_en
        assert row["unit_code"] == ind.unit_code
        assert row["topic"] == ind.topic
        assert row["source_concept"] == ind.source_concept


def _candidate(code: str, unit: str, value: str) -> Candidate:
    return Candidate(
        indicator_id=1, indicator_code=code, unit_id=1, unit_code=unit,
        period_id=1, year=2021, value=Decimal(value),
    )


def test_quality_gate_census_bands() -> None:
    ok = [
        _candidate("CENSUS_POP_TOTAL", "PERSONS", "5658"),  # Manang-sized is legit
        _candidate("CENSUS_SEX_RATIO", "RATIO", "95.59"),
        _candidate("CENSUS_POP_DENSITY", "PER_KM2", "5169"),
        _candidate("CENSUS_POP_GROWTH", "PCT", "-1.39"),  # districts can shrink
        _candidate("CENSUS_LITERACY_RATE", "PCT", "76.2"),
    ]
    assert run_quality_gate(ok).passed

    for bad in [
        _candidate("CENSUS_POP_TOTAL", "PERSONS", "99000000"),  # > Nepal x3
        _candidate("CENSUS_SEX_RATIO", "RATIO", "9559"),  # misplaced decimal
        _candidate("CENSUS_POP_DENSITY", "PER_KM2", "0"),
        _candidate("CENSUS_POP_GROWTH", "PCT", "92"),  # rate, not a share
        _candidate("CENSUS_LITERACY_RATE", "PCT", "762"),  # misplaced decimal
    ]:
        result = run_quality_gate([bad])
        assert not result.passed, f"expected failure for {bad.indicator_code}={bad.value}"
