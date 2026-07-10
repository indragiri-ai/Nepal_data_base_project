"""Offline tests for the NRB BFS table-C4 layout parser (no network, no DB).

Fixture rows use REAL label strings observed in the 59 published files
(2021-2026 scan) — including the footnote-marker variants — so these tests
lock in exactly the wobble the normalizer must absorb.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from ingestion.nrb.bfs_layout import (
    REGISTRY,
    BfsParseError,
    normalize_label,
    parse_c4,
    parse_period,
)

# ---------------------------------------------------------------------------
# normalize_label: absorbs footnote markers/spacing, never merges concepts
# ---------------------------------------------------------------------------


def test_normalizer_absorbs_footnote_variants() -> None:
    # Real variants from the published files, per normalized key.
    assert normalize_label("NPL/ Total Loan^") == normalize_label("NPL/ Total Loan")
    assert normalize_label("Total Credit/ Total Deposit**") == normalize_label(
        "Total Credit/ Total Deposit"
    )
    assert normalize_label("(a)  Saving") == normalize_label("(a) Saving")
    assert normalize_label("CD Ratio*") == normalize_label("CD Ratio#") == "cdratio"


def test_ccd_and_cd_stay_separate_indicators() -> None:
    # CCD (credit to core-capital-plus-deposit, abolished 2022) and CD
    # (credit to deposit) are different regulatory concepts.
    assert normalize_label("CCD Ratio#") != normalize_label("CD Ratio*")
    assert REGISTRY["ccdratio"].code == "NRB_BFS_CCD_RATIO"
    assert REGISTRY["cdratio"].code == "NRB_BFS_CD_RATIO"


# ---------------------------------------------------------------------------
# parse_period: both NRB title phrasings and romanization variants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("as on Baisakh End, 2083 (Mid-May, 2026)", (2083, 1)),
        ("as on Asar End, 2078 (Mid-July, 2021)", (2078, 3)),
        ("as on Ashadh End, 2079", (2079, 3)),
        ("as on Poush End, 2080 (Mid-Jan, 2024)", (2080, 9)),
        ("no period here", None),
    ],
)
def test_parse_period(text: str, expected: tuple[int, int] | None) -> None:
    assert parse_period(text) == expected


# ---------------------------------------------------------------------------
# parse_c4 on fixture matrices (columns A..G, as read from the sheet)
# ---------------------------------------------------------------------------

_E = None  # visual shorthand for an empty cell


def _matrix_2026_style() -> list[tuple[object, ...]]:
    return [
        (_E, _E, _E, _E, _E, _E, _E),
        (_E, "Major Financial Indicators", _E, _E, _E, _E, _E),
        (_E, "as on Baisakh End, 2083 (Mid-May, 2026)", _E, _E, _E, _E, _E),
        (_E, _E, _E, 'Class "A"', 'Class "B"', 'Class "C"', "Overall"),
        (_E, "A.  Credit, Deposit Ratios (%)", _E, _E, _E, _E, _E),
        (_E, 1, "Total Deposit/GDP", 117.85, 10.55, 2.28, 130.67),
        (_E, 4, " CD Ratio*", 72.02, 84.11, 76.16, 73.06),
        (_E, 9, " NPL/ Total Loan^", 5.41, 6.13, 12.19, 5.60),
        (_E, "E.  Interest Rate(%)", _E, _E, _E, _E, _E),
        (_E, 1, "Wt. Avg Interest Rate on Deposit", 3.35, _E, _E, _E),
        (_E, "Note:", _E, _E, _E, _E, _E),
    ]


def _matrix_2021_style() -> list[tuple[object, ...]]:
    return [
        (_E, "Major Financial Indicators", _E, _E, _E, _E, _E),
        (_E, "as on Asar End, 2078 (Mid-July, 2021)", _E, _E, _E, _E, _E),
        (_E, _E, _E, 'Class "A"', 'Class "B"', 'Class "C"', "Overall"),
        (_E, 4, " CCD Ratio#", 76.28, 78.39, 68.41, 76.32),
        (_E, 9, " NPL/ Total Loan", 1.41, 1.30, 6.19, 1.48),
        (_E, 3, "Wt. Average Spread Rate", 3.67, _E, _E, _E),
    ]


def test_parse_c4_2026_style() -> None:
    parsed = parse_c4(_matrix_2026_style())
    assert (parsed.bs_year, parsed.bs_month) == (2083, 1)
    assert parsed.unmatched_labels == []
    by_key = {(v.indicator_code, v.bfi_class): v.value for v in parsed.values}
    # 3 full rows x 4 classes + 1 interest-rate row (column D only) = 13 values
    assert len(parsed.values) == 13
    assert by_key[("NRB_BFS_DEPOSIT_TO_GDP", "overall")] == 130.67
    assert by_key[("NRB_BFS_CD_RATIO", "commercial_banks")] == 72.02
    assert by_key[("NRB_BFS_NPL_RATIO", "finance_companies")] == 12.19
    assert by_key[("NRB_BFS_DEPOSIT_RATE", "commercial_banks")] == 3.35
    assert ("NRB_BFS_DEPOSIT_RATE", "overall") not in by_key  # E-section: col D only


def test_parse_c4_2021_style_era() -> None:
    parsed = parse_c4(_matrix_2021_style())
    assert (parsed.bs_year, parsed.bs_month) == (2078, 3)
    by_key = {(v.indicator_code, v.bfi_class): v.value for v in parsed.values}
    assert by_key[("NRB_BFS_CCD_RATIO", "overall")] == 76.32       # CCD era
    assert ("NRB_BFS_CD_RATIO", "overall") not in by_key           # no CD yet
    assert by_key[("NRB_BFS_SPREAD_RATE", "commercial_banks")] == 3.67


def test_parse_c4_reports_unknown_labels_never_guesses() -> None:
    rows = _matrix_2026_style()
    rows.insert(6, (_E, 99, "Some Brand New Ratio", 1.0, 2.0, 3.0, 4.0))
    parsed = parse_c4(rows)
    assert parsed.unmatched_labels == ["Some Brand New Ratio"]
    assert all(v.indicator_code != "Some Brand New Ratio" for v in parsed.values)


def test_parse_c4_without_title_fails_loudly() -> None:
    with pytest.raises(BfsParseError):
        parse_c4([(_E, "no period line here", _E, _E, _E, _E, _E)])


# ---------------------------------------------------------------------------
# The seed CSV is generated from REGISTRY — they must never drift apart.
# ---------------------------------------------------------------------------


def test_seed_csv_matches_registry() -> None:
    csv_path = Path("db/seeds/indicators_nrb.csv")
    with csv_path.open(encoding="utf-8", newline="") as fh:
        rows = {r["code"]: r for r in csv.DictReader(fh)}
    registry_by_code = {spec.code: (key, spec) for key, spec in REGISTRY.items()}
    assert set(rows) == set(registry_by_code), "CSV and REGISTRY list different indicators"
    for code, row in rows.items():
        key, spec = registry_by_code[code]
        assert row["name_en"] == spec.name_en
        assert row["definition_en"] == spec.definition_en
        assert row["unit_code"] == spec.unit_code
        assert row["source_concept"] == f"BFS.C4.{key}"
        assert row["topic"] == "economy"


def test_registry_codes_are_unique_and_well_formed() -> None:
    codes = [spec.code for spec in REGISTRY.values()]
    assert len(codes) == len(set(codes))
    assert all(c.startswith("NRB_BFS_") for c in codes)
    assert all(spec.unit_code in ("PCT", "COUNT") for spec in REGISTRY.values())
