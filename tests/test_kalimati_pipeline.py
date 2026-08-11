"""ODN.S2 loader tests. Offline: no network, no database.

What is checked here is the part that decides WHAT gets stored — the basket
file, and the rules about which rows and which statistics are eligible. The
database work itself is exercised by the dry run against the live warehouse.
"""

from __future__ import annotations

import csv
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ingestion.opendatanepal.kalimati_acquire import KalimatiError, PriceRow
from ingestion.opendatanepal.kalimati_pipeline import (
    BASKET_CSV,
    GEO_CODE,
    MAX_INDICATOR,
    MIN_INDICATOR,
    SEED_CSV,
    UNIT_CODE,
    read_basket,
)


def _row(commodity: str, unit: str = "Kg") -> PriceRow:
    return PriceRow(
        commodity=commodity,
        day=date(2020, 1, 1),
        unit=unit,
        minimum=Decimal("10"),
        maximum=Decimal("20"),
        midpoint=Decimal("15"),
    )


# --- the basket, as reviewable data (rule 4) ---------------------------------


def test_the_basket_file_exists_and_lists_the_curated_commodities() -> None:
    basket = read_basket()
    assert len(basket) == 25
    # Ranked by how many days each appears, so the staples lead.
    assert "Cauli Local" in basket
    assert "Potato Red" in basket
    assert "Tomato Small(Local)" in basket


def test_the_basket_can_be_trimmed_for_a_rehearsal() -> None:
    assert len(read_basket(limit=3)) == 3


def test_every_basket_row_carries_its_evidence() -> None:
    """The CSV records how many days each commodity appears on.

    That number is why the commodity is in the basket at all; keeping it beside
    the name means a human can argue with the selection instead of taking it on
    trust.
    """
    with BASKET_CSV.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 25
    for row in rows:
        assert int(row["days_present"]) > 0


# --- what the loader stores --------------------------------------------------


def test_the_low_high_pair_is_never_presented_as_an_average() -> None:
    """The re-published 'Average' column is not loaded, and never named one.

    It is exactly (min + max) / 2 across the whole series and disagrees with
    the market board's own published average. Only a figure that really is an
    average may carry the word — and only one does: KALIMATI_PRICE_AVG, which
    comes from the board itself and says so in its own name.
    """
    with SEED_CSV.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    codes = {r["code"] for r in rows}
    assert codes == {MIN_INDICATOR, MAX_INDICATOR, "KALIMATI_PRICE_AVG"}

    by_code = {r["code"]: r for r in rows}
    for code in (MIN_INDICATOR, MAX_INDICATOR):
        assert "average" not in by_code[code]["name_en"].lower()
    # The one that IS an average names its author, so no reader can mistake it
    # for something this portal computed.
    assert "market board average" in by_code["KALIMATI_PRICE_AVG"]["name_en"].lower()
    for row in rows:
        assert row["unit"] == UNIT_CODE


def test_the_board_average_definition_explains_it_is_not_a_midpoint() -> None:
    # The whole reason it is a separate series rather than an extension of the
    # low/high pair: they are different statistics.
    with SEED_CSV.open(encoding="utf-8", newline="") as fh:
        row = next(r for r in csv.DictReader(fh) if r["code"] == "KALIMATI_PRICE_AVG")
    text = row["definition_en"].lower()
    assert "not the midpoint" in text
    assert "continues to the present" in text


def test_the_definitions_state_the_closed_coverage_window() -> None:
    # Vintage honesty: a historical series must never read as current prices.
    text = SEED_CSV.read_text(encoding="utf-8")
    assert "2022-04-18" in text
    assert "NOT" in text and "current prices" in text


def test_the_definitions_explain_the_kg_only_rule() -> None:
    text = SEED_CSV.read_text(encoding="utf-8").lower()
    assert "per piece or per dozen are excluded" in text


def test_prices_are_filed_where_the_market_is_not_nationally() -> None:
    """One market's wholesale prices are not Nepal's prices.

    NP0327101 is Kathmandu Metropolitan City, where Kalimati market sits.
    """
    assert GEO_CODE == "NP0327101"
    assert not GEO_CODE == "NP"


# --- the rules the loader applies to rows ------------------------------------


def test_non_kg_rows_never_reach_the_warehouse() -> None:
    rows = [_row("Cauli Local"), _row("Coconut", unit="1 Pc")]
    basket = {"Cauli Local", "Coconut"}
    eligible = [r for r in rows if r.unit.lower() == "kg" and r.commodity in basket]
    assert [r.commodity for r in eligible] == ["Cauli Local"]


def test_commodities_outside_the_basket_are_left_out() -> None:
    rows = [_row("Cauli Local"), _row("Dragon Fruit")]
    basket = {"Cauli Local"}
    eligible = [r for r in rows if r.unit.lower() == "kg" and r.commodity in basket]
    assert [r.commodity for r in eligible] == ["Cauli Local"]


def test_a_missing_basket_file_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    import ingestion.opendatanepal.kalimati_pipeline as pipeline

    monkeypatch.setattr(pipeline, "BASKET_CSV", Path("db/seeds/does-not-exist.csv"))
    with pytest.raises(KalimatiError, match="is missing"):
        pipeline.read_basket()


# --- the overlap between the two resources -----------------------------------


def _dated(commodity: str, day: date, low: str, high: str) -> PriceRow:
    return PriceRow(
        commodity=commodity,
        day=day,
        unit="Kg",
        minimum=Decimal(low),
        maximum=Decimal(high),
        midpoint=(Decimal(low) + Decimal(high)) / 2,
    )


def test_a_commodity_day_appearing_in_both_resources_is_stored_once() -> None:
    """The two resources overlap by about four months.

    Offering the same cell twice is rejected by the database's uniqueness
    constraint — which is right, because the alternative is a silently
    double-counted price. It caught exactly this on the first real load.
    """
    from ingestion.opendatanepal.kalimati_pipeline import deduplicate

    day = date(2021, 3, 15)
    rows = [_dated("Tomato", day, "25", "30"), _dated("Tomato", day, "25", "30")]
    kept, overlaps, conflicts = deduplicate(rows)
    assert len(kept) == 1
    assert overlaps == 1
    assert conflicts == []


def test_the_later_resource_wins_a_disagreement_and_it_is_reported() -> None:
    # Preferring the newer publication is the step file's tie-break; the point
    # is that the disagreement is counted rather than silently resolved.
    from ingestion.opendatanepal.kalimati_pipeline import deduplicate

    day = date(2021, 3, 15)
    rows = [_dated("Tomato", day, "25", "30"), _dated("Tomato", day, "26", "31")]
    kept, overlaps, conflicts = deduplicate(rows)
    assert kept[0].minimum == Decimal("26")  # the later row
    assert overlaps == 1
    assert len(conflicts) == 1
    assert "Tomato" in conflicts[0]


def test_different_days_and_commodities_are_never_merged() -> None:
    from ingestion.opendatanepal.kalimati_pipeline import deduplicate

    rows = [
        _dated("Tomato", date(2021, 3, 15), "25", "30"),
        _dated("Tomato", date(2021, 3, 16), "26", "31"),
        _dated("Potato", date(2021, 3, 15), "40", "45"),
    ]
    kept, overlaps, conflicts = deduplicate(rows)
    assert len(kept) == 3
    assert overlaps == 0


def test_the_frontend_basket_matches_the_seed_csv() -> None:
    """The commodity picker lists the same basket the loader loaded.

    The panel hard-codes the list (it is a client component with no build-time
    access to db/seeds), so the two can drift — and a picker offering a
    commodity that was never loaded shows a reader an empty chart. This test is
    the seam that catches it.
    """
    panel = Path("web/components/MarketPricesPanel.tsx").read_text(encoding="utf-8")
    block = panel.split("const BASKET = [", 1)[1].split("] as const", 1)[0]
    in_panel = re.findall(r'"([^"]+)"', block)

    with BASKET_CSV.open(encoding="utf-8", newline="") as fh:
        in_csv = [row["commodity"] for row in csv.DictReader(fh)]

    assert in_panel == in_csv, (
        "the commodity picker and db/seeds/kalimati_basket.csv have drifted"
    )


# --- every database run is visible to /v1/meta ------------------------------


class _LogCursor:
    """Small SQL-aware cursor for the pipeline's offline logging tests."""

    def __init__(self, latest: list[tuple[int, int, str, Decimal]] | None = None) -> None:
        self.latest = latest or []
        self.calls: list[tuple[str, Any]] = []
        self._one: tuple[int] | None = None
        self._many: list[tuple[Any, ...]] = []

    def __enter__(self) -> _LogCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> None:
        compact = " ".join(sql.split())
        self.calls.append((compact, params))
        self._one = None
        self._many = []
        if compact.startswith("SELECT id FROM units"):
            self._one = (30,)
        elif compact.startswith("SELECT id FROM geographies"):
            self._one = (40,)
        elif compact.startswith("INSERT INTO sources"):
            self._one = (10,)
        elif compact.startswith("INSERT INTO datasets"):
            self._one = (20,)
        elif compact.startswith("SELECT source_id FROM datasets"):
            self._one = (10,)
        elif compact.startswith("SELECT code, id FROM indicators"):
            self._many = [(MIN_INDICATOR, 101), (MAX_INDICATOR, 102)]
        elif compact.startswith("SELECT gregorian_start, id FROM time_periods"):
            self._many = [(date(2020, 1, 1), 103)]
        elif compact.startswith("SELECT o.indicator_id"):
            self._many = list(self.latest)
        elif compact.startswith("INSERT INTO releases"):
            self._one = (60,)
        elif compact.startswith("INSERT INTO ingestion_log") and "RETURNING id" in compact:
            self._one = (70,)

    def executemany(self, sql: str, params: Any) -> None:
        self.calls.append((" ".join(sql.split()), list(params)))

    def fetchone(self) -> tuple[int] | None:
        return self._one

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._many


class _LogConnection:
    def __init__(self, cursor: _LogCursor) -> None:
        self._cursor = cursor
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self) -> _LogConnection:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def cursor(self) -> _LogCursor:
        return self._cursor

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _use_fake_database(
    monkeypatch: pytest.MonkeyPatch,
    latest: list[tuple[int, int, str, Decimal]] | None = None,
) -> tuple[_LogCursor, _LogConnection]:
    import ingestion.opendatanepal.kalimati_pipeline as pipeline

    cursor = _LogCursor(latest)
    connection = _LogConnection(cursor)
    monkeypatch.setenv("DATABASE_URL", "postgresql://offline-test")
    monkeypatch.setattr(pipeline.psycopg, "connect", lambda _dsn: connection)
    return cursor, connection


def _matching_calls(cursor: _LogCursor, phrase: str) -> list[tuple[str, Any]]:
    return [call for call in cursor.calls if phrase in call[0]]


def test_a_load_records_running_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import ingestion.opendatanepal.kalimati_pipeline as pipeline

    cursor, connection = _use_fake_database(monkeypatch)

    loaded = pipeline.load(
        [_row("Cauli Local")],
        ["Cauli Local"],
        dry_run=False,
        raw_refs=["raw/kalimati.json"],
    )

    assert loaded == 2
    running = _matching_calls(cursor, "VALUES (%s, %s, 'running'")
    assert running and running[0][1] == (20, 60, '["raw/kalimati.json"]')
    success = _matching_calls(cursor, "UPDATE ingestion_log SET status = 'success'")
    assert success and success[0][1] == (2, 2, 70)
    assert connection.commits >= 3


def test_a_noop_rerun_still_records_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import ingestion.opendatanepal.kalimati_pipeline as pipeline

    latest = [
        (101, 103, "Cauli Local", Decimal("10")),
        (102, 103, "Cauli Local", Decimal("20")),
    ]
    cursor, _connection = _use_fake_database(monkeypatch, latest)

    loaded = pipeline.load(
        [_row("Cauli Local")],
        ["Cauli Local"],
        dry_run=False,
        raw_refs=["raw/noop.json"],
    )

    assert loaded == 0
    success = _matching_calls(cursor, "VALUES (%s, 'success', now(), %s, 0, 0")
    assert success and success[0][1] == (20, 2, '["raw/noop.json"]')
    assert not _matching_calls(cursor, "INSERT INTO releases")


def test_a_raw_archive_failure_is_logged(monkeypatch: pytest.MonkeyPatch) -> None:
    import ingestion.opendatanepal.kalimati_pipeline as pipeline
    from ingestion.common.raw_lake import RawLakeError

    cursor, connection = _use_fake_database(monkeypatch)

    pipeline.record_raw_archive_failure(
        ["raw/first-resource.json"],
        RawLakeError("second resource upload failed"),
    )

    failed = _matching_calls(cursor, "VALUES (%s, 'failed', now(), 0, 0, 0")
    assert failed
    assert failed[0][1][0:2] == (20, '["raw/first-resource.json"]')
    assert "second resource upload failed" in failed[0][1][2]
    assert connection.commits == 1
