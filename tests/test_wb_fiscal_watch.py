"""WBF.S4 update-watcher tests. Offline: no network, no database.

The watcher's job is to notice that the source moved and to say what moved.
Both halves are pure functions over harvested rows, which is why they can be
tested without touching the World Bank.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from ingestion.worldbank.fiscal_pipeline import Row
from ingestion.worldbank.fiscal_watch import (
    FiscalWatchError,
    describe_changes,
    fingerprint,
    period_year,
    read_stored,
    write_stored,
)


def _rows(code: str, pairs: list[tuple[str, str]]) -> list[Row]:
    return [Row(indicator_code=code, period_label=p, value=Decimal(v)) for p, v in pairs]


# --- the fingerprint ---------------------------------------------------------


def test_fingerprint_records_years_latest_period_and_value() -> None:
    rows = _rows(
        "FISCAL_REVENUE_ACTUAL",
        [("FY 2021/22", "1000.5"), ("FY 2023/24", "979124.6"), ("FY 2022/23", "900.0")],
    )
    fp = fingerprint(rows)
    assert fp == {
        "FISCAL_REVENUE_ACTUAL": {
            "years": "3",
            "latest_period": "FY 2023/24",
            "latest_value": "979124.6",
        }
    }


def test_fingerprint_picks_the_newest_year_not_the_last_row() -> None:
    # Harvest order is the source's, not chronological; the newest year must be
    # chosen by the year, or a reordered response would look like a revision.
    rows = _rows("X", [("FY 2023/24", "5"), ("FY 2017/18", "1")])
    assert fingerprint(rows)["X"]["latest_period"] == "FY 2023/24"


def test_fingerprint_keeps_series_apart() -> None:
    rows = _rows("A", [("FY 2023/24", "1")]) + _rows("B", [("FY 2022/23", "2")])
    fp = fingerprint(rows)
    assert set(fp) == {"A", "B"}
    assert fp["B"]["latest_period"] == "FY 2022/23"


def test_an_unexpected_period_label_fails_loudly() -> None:
    # Rule 1: a changed labelling scheme is reported, never guessed past — the
    # comparison that follows would otherwise be meaningless.
    with pytest.raises(FiscalWatchError, match="unexpected period label"):
        period_year("2023-24")


def test_period_year_reads_the_gregorian_start_year() -> None:
    assert period_year("FY 2023/24") == 2023


# --- what changed ------------------------------------------------------------


def test_no_changes_reads_as_no_changes() -> None:
    fp = fingerprint(_rows("A", [("FY 2023/24", "10")]))
    assert describe_changes(fp, fp) == []


def test_a_new_fiscal_year_is_reported_as_a_new_year() -> None:
    old = fingerprint(_rows("A", [("FY 2023/24", "10")]))
    new = fingerprint(_rows("A", [("FY 2023/24", "10"), ("FY 2024/25", "12")]))
    (line,) = describe_changes(old, new)
    assert "NEW YEAR" in line
    assert "FY 2023/24 -> FY 2024/25" in line


def test_a_revised_value_is_reported_as_a_revision() -> None:
    old = fingerprint(_rows("A", [("FY 2023/24", "10")]))
    new = fingerprint(_rows("A", [("FY 2023/24", "11")]))
    (line,) = describe_changes(old, new)
    assert "REVISED" in line
    assert "10 -> 11" in line


def test_a_new_series_and_a_vanished_series_are_both_reported() -> None:
    old = fingerprint(_rows("GONE", [("FY 2023/24", "1")]))
    new = fingerprint(_rows("ADDED", [("FY 2023/24", "2")]))
    lines = describe_changes(old, new)
    assert any("NEW SERIES  ADDED" in ln for ln in lines)
    assert any("SERIES GONE GONE" in ln for ln in lines)


def test_a_dropped_older_year_is_noticed_even_when_the_latest_is_unchanged() -> None:
    # Same newest year, same value, one year fewer: the source lost history.
    old = fingerprint(_rows("A", [("FY 2022/23", "9"), ("FY 2023/24", "10")]))
    new = fingerprint(_rows("A", [("FY 2023/24", "10")]))
    (line,) = describe_changes(old, new)
    assert "YEAR COUNT" in line
    assert "2 -> 1" in line


# --- the stored baseline -----------------------------------------------------


def test_a_written_baseline_reads_back_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "watch_fingerprint.json"
    fp = fingerprint(_rows("A", [("FY 2023/24", "10")]))
    write_stored(path, fp, "2026-08-06")
    assert read_stored(path) == fp


def test_a_missing_baseline_reads_as_none_not_an_error(tmp_path: Path) -> None:
    # First run has nothing to compare against; that is not a failure.
    assert read_stored(tmp_path / "nope.json") is None


def test_a_corrupt_baseline_refuses_to_compare(tmp_path: Path) -> None:
    # Silently treating an unreadable baseline as "no change" would turn the
    # watcher into decoration.
    path = tmp_path / "watch_fingerprint.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(FiscalWatchError, match="not valid JSON"):
        read_stored(path)


def test_a_baseline_without_series_refuses_to_compare(tmp_path: Path) -> None:
    path = tmp_path / "watch_fingerprint.json"
    path.write_text(json.dumps({"checked_at": "2026-08-06"}), encoding="utf-8")
    with pytest.raises(FiscalWatchError, match="no 'series' object"):
        read_stored(path)
