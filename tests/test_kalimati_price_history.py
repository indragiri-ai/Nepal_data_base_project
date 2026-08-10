"""Tests for the market board's own price history. Offline: no network, no DB.

The board's API answers with a commodity NAME alongside the numbers, which is
the one check standing between a wrong code and a decade of prices filed under
the wrong vegetable. Most of what follows guards that seam.
"""

from __future__ import annotations

import csv
import json
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from ingestion.kalimati.price_history import (
    CODES_CSV,
    MAX_PRICE,
    REQUEST_PAUSE_S,
    RETRY_BACKOFF_S,
    SERIES_START,
    AvgRow,
    KalimatiOfficialError,
    parse_payload,
    read_codes,
)


def _payload(commodity: str = "Tomato Big(Nepali)", **over: object) -> bytes:
    body: dict[str, object] = {
        "status": 200,
        "from": SERIES_START,
        "to": "2026-08-07",
        "commodity": commodity,
        "prices": {
            "date": ["2013-06-16", "2022-04-19", "2026-08-07"],
            "avg": ["38.00", "56.67", "65.00"],
        },
    }
    body.update(over)
    return json.dumps(body).encode()


# --- reading the board's response --------------------------------------------


def test_a_response_parses_into_typed_daily_averages() -> None:
    rows = parse_payload(_payload(), "101.1", "Tomato Big(Nepali)")
    assert len(rows) == 3
    assert rows[0].day == date(2013, 6, 16)
    assert rows[0].average == Decimal("38.00")
    assert rows[-1].day == date(2026, 8, 7)
    assert all(r.commodity == "Tomato Big(Nepali)" for r in rows)


def test_a_commodity_name_that_does_not_match_stops_the_run() -> None:
    """The single most valuable check in this module.

    Codes are the board's, not ours. If a code ever points somewhere else, every
    row it returns would be stored under our name for it — a decade of ginger
    prices labelled tomato. The board tells us what it thinks we asked for, so
    we compare.
    """
    with pytest.raises(KalimatiOfficialError, match="the code mapping"):
        parse_payload(_payload(commodity="Ginger"), "101.1", "Tomato Big(Nepali)")


def test_mismatched_date_and_value_counts_stop_the_run() -> None:
    bad = _payload(prices={"date": ["2013-06-16", "2013-06-17"], "avg": ["38.00"]})
    with pytest.raises(KalimatiOfficialError, match="dates but"):
        parse_payload(bad, "101.1", "Tomato Big(Nepali)")


def test_an_unreadable_date_stops_the_run() -> None:
    bad = _payload(prices={"date": ["16/06/2013"], "avg": ["38.00"]})
    with pytest.raises(KalimatiOfficialError, match="unreadable date"):
        parse_payload(bad, "101.1", "Tomato Big(Nepali)")


def test_a_non_numeric_price_stops_the_run() -> None:
    bad = _payload(prices={"date": ["2013-06-16"], "avg": ["n/a"]})
    with pytest.raises(KalimatiOfficialError, match="not a number"):
        parse_payload(bad, "101.1", "Tomato Big(Nepali)")


def test_a_thousands_separator_is_read_not_rejected() -> None:
    # A dear commodity can pass 1,000 NPR/kg; the board formats it with a comma.
    rows = parse_payload(
        _payload(prices={"date": ["2013-06-16"], "avg": ["1,250.00"]}),
        "301",
        "Tomato Big(Nepali)",
    )
    assert rows[0].average == Decimal("1250.00")


@pytest.mark.parametrize("price", ["0", "-5", "10001"])
def test_a_price_outside_the_band_stops_the_run(price: str) -> None:
    bad = _payload(prices={"date": ["2013-06-16"], "avg": [price]})
    with pytest.raises(KalimatiOfficialError, match="outside"):
        parse_payload(bad, "101.1", "Tomato Big(Nepali)")


def test_a_price_at_the_ceiling_is_allowed() -> None:
    rows = parse_payload(
        _payload(prices={"date": ["2013-06-16"], "avg": [str(MAX_PRICE)]}),
        "101.1",
        "Tomato Big(Nepali)",
    )
    assert rows[0].average == MAX_PRICE


def test_a_non_json_response_stops_the_run() -> None:
    with pytest.raises(KalimatiOfficialError, match="not JSON"):
        parse_payload(b"<html>rate limited</html>", "101.1", "Tomato Big(Nepali)")


def test_an_empty_history_is_not_an_error() -> None:
    # A commodity the board no longer trades returns no days; that is a fact
    # about the commodity, not a failure.
    rows = parse_payload(
        _payload(prices={"date": [], "avg": []}), "101.1", "Tomato Big(Nepali)"
    )
    assert rows == []


# --- the code mapping, as reviewable data ------------------------------------


def test_the_codes_seed_maps_basket_names_to_board_codes() -> None:
    codes = read_codes()
    assert len(codes) == 24
    names = {name for name, _ in codes}
    assert "Tomato Small(Local)" in names
    assert "Cauli Local" in names


def test_potato_red_is_absent_and_not_substituted() -> None:
    """The board no longer lists a plain "Potato Red".

    It offers "Potato Red(Long)" and "Potato Red(Indian)" instead. Mapping our
    historical "Potato Red" onto either would invent a continuity the sources
    do not support, so it is simply missing — and this test says so out loud.
    """
    assert "Potato Red" not in {name for name, _ in read_codes()}


def test_every_code_records_when_it_was_matched() -> None:
    with CODES_CSV.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows
    for row in rows:
        assert row["market_code"].strip()
        assert row["matched_on"].strip()


# --- being a good guest ------------------------------------------------------


def test_the_request_pause_stays_generous() -> None:
    """The board's server hung up on a run pacing at 4 seconds.

    Their page states the policy in writing. This test exists so a future
    "let's speed this up" cannot quietly reintroduce the behaviour that got the
    connection dropped.
    """
    assert REQUEST_PAUSE_S >= 10


def test_dropped_connections_keep_the_existing_courteous_backoff() -> None:
    assert RETRY_BACKOFF_S == (60.0, 180.0)


def test_the_capped_value_is_named_so_the_artefact_stays_visible() -> None:
    """The board's average tops out at 999.99.

    For 16 days of Lime in 2018 it reports exactly 999.99 while the board's own
    low and high those days were 1,000-1,500. An average cannot sit below the
    minimum, so that is a field width, not a price. The harvest counts these on
    every run and says so, which is how a known artefact stays known — and how
    a change in its size gets noticed instead of absorbed.
    """
    from ingestion.kalimati.price_history import CAP_VALUE

    assert CAP_VALUE == Decimal("999.99")
    # It is inside the accepted band on purpose: these are the board's own
    # published figures and are loaded as such, flagged rather than dropped.
    assert Decimal("0") < CAP_VALUE <= MAX_PRICE


# --- every official-market run is visible to /v1/meta -----------------------


class _LogCursor:
    def __init__(self, latest: list[tuple[int, str, Decimal]] | None = None) -> None:
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
        if compact.startswith("SELECT id FROM sources"):
            self._one = (10,)
        elif compact.startswith("INSERT INTO datasets"):
            self._one = (20,)
        elif compact.startswith("SELECT id FROM units"):
            self._one = (30,)
        elif compact.startswith("SELECT id FROM geographies"):
            self._one = (40,)
        elif compact.startswith("SELECT id FROM indicators"):
            self._one = (50,)
        elif compact.startswith("SELECT gregorian_start, id FROM time_periods"):
            self._many = [(date(2026, 8, 10), 60)]
        elif compact.startswith("SELECT o.time_period_id"):
            self._many = list(self.latest)
        elif compact.startswith("INSERT INTO releases"):
            self._one = (70,)
        elif compact.startswith("INSERT INTO ingestion_log") and "RETURNING id" in compact:
            self._one = (80,)

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

    def __enter__(self) -> _LogConnection:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def cursor(self) -> _LogCursor:
        return self._cursor

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        return None


def _use_fake_database(
    monkeypatch: pytest.MonkeyPatch,
    latest: list[tuple[int, str, Decimal]] | None = None,
) -> tuple[_LogCursor, _LogConnection]:
    import ingestion.kalimati.price_history as pipeline

    cursor = _LogCursor(latest)
    connection = _LogConnection(cursor)
    monkeypatch.setenv("DATABASE_URL", "postgresql://offline-test")
    monkeypatch.setattr(pipeline.psycopg, "connect", lambda _dsn: connection)
    return cursor, connection


def _matching_calls(cursor: _LogCursor, phrase: str) -> list[tuple[str, Any]]:
    return [call for call in cursor.calls if phrase in call[0]]


def _today_row() -> AvgRow:
    return AvgRow("Tomato Big(Nepali)", date(2026, 8, 10), Decimal("65"))


def test_an_official_market_load_records_running_then_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ingestion.kalimati.price_history as pipeline

    cursor, connection = _use_fake_database(monkeypatch)
    loaded = pipeline.load(
        [_today_row()], dry_run=False, raw_refs=["raw/official-snapshot.json"]
    )

    assert loaded == 1
    running = _matching_calls(cursor, "VALUES (%s, %s, 'running'")
    assert running and running[0][1] == (20, 70, '["raw/official-snapshot.json"]')
    success = _matching_calls(cursor, "UPDATE ingestion_log SET status = 'success'")
    assert success and success[0][1] == (1, 1, 80)
    assert connection.commits >= 3


def test_an_official_market_noop_still_records_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ingestion.kalimati.price_history as pipeline

    cursor, _connection = _use_fake_database(
        monkeypatch, [(60, "Tomato Big(Nepali)", Decimal("65"))]
    )
    loaded = pipeline.load([_today_row()], dry_run=False, raw_refs=["raw/noop.json"])

    assert loaded == 0
    success = _matching_calls(cursor, "VALUES (%s, 'success', now(), %s, 0, 0")
    assert success and success[0][1] == (20, 1, '["raw/noop.json"]')
    assert not _matching_calls(cursor, "INSERT INTO releases")
