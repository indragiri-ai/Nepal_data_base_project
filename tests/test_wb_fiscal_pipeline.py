"""Federal fiscal loader logging tests. Offline: no network or database."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest

from ingestion.worldbank.fiscal_pipeline import Row


class _LogCursor:
    def __init__(self, latest: list[tuple[int, int, Decimal]] | None = None) -> None:
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
        elif compact.startswith("SELECT id FROM datasets"):
            self._one = (20,)
        elif compact.startswith("SELECT code, id FROM units"):
            self._many = [("NPR_MILLION", 30)]
        elif compact.startswith("SELECT code, id FROM indicators"):
            self._many = [("FISCAL_REVENUE_ACTUAL", 101)]
        elif compact.startswith("SELECT id FROM geographies"):
            self._one = (40,)
        elif compact.startswith("SELECT id FROM units"):
            self._one = (30,)
        elif compact.startswith("SELECT gregorian_label, id FROM time_periods"):
            self._many = [("FY 2023/24", 103)]
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


@dataclass(frozen=True)
class _Stored:
    payload_path: str = "worldbank/fiscal-dashboard/raw.json"
    size_bytes: int = 123


class _Archive:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls: list[tuple[str, list[tuple[str, bytes, str]], str]] = []

    def store_snapshot(
        self,
        dataset_code: str,
        members: list[tuple[str, bytes, str]],
        snapshot_filename: str,
    ) -> _Stored:
        self.calls.append((dataset_code, members, snapshot_filename))
        if self.failure is not None:
            raise self.failure
        return _Stored()


def _use_fakes(
    monkeypatch: pytest.MonkeyPatch,
    latest: list[tuple[int, int, Decimal]] | None = None,
    archive_failure: Exception | None = None,
) -> tuple[_LogCursor, _LogConnection, _Archive]:
    import ingestion.worldbank.fiscal_pipeline as pipeline

    cursor = _LogCursor(latest)
    connection = _LogConnection(cursor)
    archive = _Archive(archive_failure)
    monkeypatch.setenv("DATABASE_URL", "postgresql://offline-test")
    monkeypatch.setattr(pipeline.psycopg, "connect", lambda _dsn: connection)
    monkeypatch.setattr(pipeline.RawLake, "from_env", lambda: archive)
    return cursor, connection, archive


def _calls(cursor: _LogCursor, phrase: str) -> list[tuple[str, Any]]:
    return [call for call in cursor.calls if phrase in call[0]]


def _row() -> Row:
    return Row("FISCAL_REVENUE_ACTUAL", "FY 2023/24", Decimal("1000"))


RAW_MEMBERS = [("revenue.csv", b"raw,csv\n", "https://example.test/revenue.csv")]


def test_a_load_records_running_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import ingestion.worldbank.fiscal_pipeline as pipeline

    cursor, connection, archive = _use_fakes(monkeypatch)

    pipeline.load([_row()], dry_run=False, raw_members=RAW_MEMBERS)

    assert archive.calls[0][1] == RAW_MEMBERS
    running = _calls(cursor, "VALUES (%s, %s, 'running'")
    assert running and running[0][1] == (
        20,
        60,
        '["worldbank/fiscal-dashboard/raw.json"]',
    )
    success = _calls(cursor, "UPDATE ingestion_log SET status = 'success'")
    assert success and success[0][1] == (1, 1, 70)
    assert connection.commits >= 3


def test_a_noop_rerun_still_records_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import ingestion.worldbank.fiscal_pipeline as pipeline

    cursor, _connection, _archive = _use_fakes(
        monkeypatch,
        latest=[(101, 103, Decimal("1000"))],
    )

    pipeline.load([_row()], dry_run=False, raw_members=RAW_MEMBERS)

    success = _calls(cursor, "VALUES (%s, 'success', now(), %s, 0, 0")
    assert success and success[0][1] == (
        20,
        1,
        '["worldbank/fiscal-dashboard/raw.json"]',
    )
    assert not _calls(cursor, "INSERT INTO releases")


def test_a_raw_archive_failure_is_logged(monkeypatch: pytest.MonkeyPatch) -> None:
    import ingestion.worldbank.fiscal_pipeline as pipeline
    from ingestion.common.raw_lake import RawLakeError

    cursor, connection, _archive = _use_fakes(
        monkeypatch,
        archive_failure=RawLakeError("storage unavailable"),
    )

    with pytest.raises(pipeline.FiscalLoadError, match="nothing was loaded"):
        pipeline.load([_row()], dry_run=False, raw_members=RAW_MEMBERS)

    failed = _calls(cursor, "VALUES (%s, 'failed', now(), %s, 0")
    assert failed
    assert failed[0][1][0:2] == (20, 1)
    assert "storage unavailable" in failed[0][1][2]
    assert not _calls(cursor, "INSERT INTO releases")
    assert connection.commits == 1


def test_harvest_retains_the_untouched_csv_for_archiving(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ingestion.worldbank.fiscal_pipeline as pipeline
    from ingestion.worldbank.fiscal_acquire import SheetPayload

    monkeypatch.setattr(pipeline, "FEDERAL_SHEETS", (pipeline.FEDERAL_SHEETS[0],))
    monkeypatch.setattr(pipeline, "open_session", lambda: object())
    monkeypatch.setattr(pipeline.time, "sleep", lambda _seconds: None)

    def fake_fetch(_session: object, sheet: str, filters: dict[str, str]) -> SheetPayload:
        measure_type = filters["Type1"]
        content = f"Year1,value\nFY2024,{1000 if measure_type == 'Actual' else 1100}\n".encode()
        return SheetPayload(
            sheet=sheet,
            view="FederalRevenue",
            source_url=f"https://example.test/{measure_type.lower()}.csv",
            content=content,
        )

    monkeypatch.setattr(pipeline, "fetch_sheet", fake_fetch)
    raw_members: list[tuple[str, bytes, str]] = []

    rows = pipeline.harvest(raw_members)

    assert len(rows) == 2
    assert [member[0] for member in raw_members] == [
        "FederalRevenue_actual.csv",
        "FederalRevenue_budget.csv",
    ]
    assert raw_members[0][1].startswith(b"Year1,value\n")
