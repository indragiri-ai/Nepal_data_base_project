"""WBF.S2 provincial-loader tests. Offline: no network, no database."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest

from ingestion.worldbank.fiscal_layout import PROVINCE_CODES
from ingestion.worldbank.fiscal_pipeline import FiscalLoadError
from ingestion.worldbank.fiscal_provincial import (
    SHEETS,
    SUM_TOLERANCE,
    TYPES,
    ProvRow,
    _bkey,
    _category_column,
)


def test_category_column_handles_both_header_shapes() -> None:
    # The Grants sheet names its columns differently from Revenue/Expenditure.
    plain = ["Group2", "measure_%TOT_G3", "Fiscal year", "Group0"]
    grants = ["Group2 (Prov!Grant)", "grant_%TOT_G3", "Fiscal year (prov!grant)"]
    assert _category_column(plain) == 0
    assert _category_column(grants) == 0


def test_category_column_fails_loudly_on_an_unknown_header() -> None:
    # A renamed column must stop the load, not silently index the wrong field.
    with pytest.raises(FiscalLoadError, match="no category column"):
        _category_column(["Year1", "value", "Something else"])


def test_breakdown_key_is_stable_across_orderings() -> None:
    # The idempotency check compares Python dicts against Postgres jsonb, which
    # reorders keys; the key must not depend on insertion order.
    assert _bkey({"category": "Taxes"}) == _bkey({"category": "Taxes"})
    assert _bkey({}) == "{}"
    assert json.loads(_bkey({"category": "Grants"})) == {"category": "Grants"}


def test_a_headline_row_carries_no_category() -> None:
    # breakdowns = {} is what /v1/data/geo filters on for the choropleth.
    total = ProvRow("FISCAL_PROV_REVENUE_ACTUAL", "NP03", "FY 2023/24", "", Decimal("1"))
    part = ProvRow("FISCAL_PROV_REVENUE_ACTUAL", "NP03", "FY 2023/24", "Taxes", Decimal("1"))
    assert total.category == ""
    assert part.category == "Taxes"


def test_the_cross_check_would_catch_a_missing_province() -> None:
    """The gate that makes a derived provincial total safe to publish.

    Reproduces the spike's real figures: the seven provinces' FY2024 tax
    revenue sums to the published all-provinces total exactly. Drop one
    province and the gate must fire.
    """
    per_province = [
        Decimal("12320.47"), Decimal("11275.08"), Decimal("20704.84"),
        Decimal("12907.97"), Decimal("11828.10"), Decimal("7766.79"),
        Decimal("8166.11"),
    ]
    published_national = Decimal("84969.36")

    assert abs(sum(per_province) - published_national) <= SUM_TOLERANCE

    missing_one = sum(per_province[:-1])
    assert abs(missing_one - published_national) > SUM_TOLERANCE


def test_every_province_is_covered() -> None:
    assert len(PROVINCE_CODES) == 7


def test_sheets_and_types_are_declared_explicitly() -> None:
    # Scope is a deliberate choice, not an accident: three sheets, both types.
    assert TYPES == ("Actual", "Budget")
    assert len(SHEETS) == 3
    prefixes = [prefix for _, prefix in SHEETS]
    assert len(set(prefixes)) == len(prefixes), "indicator prefixes must be unique"
    for sheet, prefix in SHEETS:
        assert sheet.startswith("Provincial")
        assert prefix.startswith("FISCAL_PROV_")


# --- every database run is visible to /v1/meta ------------------------------


class _LogCursor:
    def __init__(
        self,
        latest: list[tuple[int, int, int, str, Decimal]] | None = None,
    ) -> None:
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
        elif compact.startswith("SELECT code, id FROM indicators"):
            self._many = [("FISCAL_PROV_REVENUE_ACTUAL", 101)]
        elif compact.startswith("SELECT code, id FROM geographies"):
            self._many = [("NP03", 40)]
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
    payload_path: str = "worldbank/fiscal-dashboard/provincial.json"
    size_bytes: int = 456


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
    latest: list[tuple[int, int, int, str, Decimal]] | None = None,
    archive_failure: Exception | None = None,
) -> tuple[_LogCursor, _LogConnection, _Archive]:
    import ingestion.worldbank.fiscal_provincial as pipeline

    cursor = _LogCursor(latest)
    connection = _LogConnection(cursor)
    archive = _Archive(archive_failure)
    monkeypatch.setenv("DATABASE_URL", "postgresql://offline-test")
    monkeypatch.setattr(pipeline.psycopg, "connect", lambda _dsn: connection)
    monkeypatch.setattr(pipeline, "seed_indicators", lambda _cur, _source_id: 1)
    monkeypatch.setattr(pipeline.RawLake, "from_env", lambda: archive)
    return cursor, connection, archive


def _calls(cursor: _LogCursor, phrase: str) -> list[tuple[str, Any]]:
    return [call for call in cursor.calls if phrase in call[0]]


def _row() -> ProvRow:
    return ProvRow(
        "FISCAL_PROV_REVENUE_ACTUAL",
        "NP03",
        "FY 2023/24",
        "",
        Decimal("1000"),
    )


RAW_MEMBERS = [("province.csv", b"raw,csv\n", "https://example.test/province.csv")]


def test_a_load_records_running_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import ingestion.worldbank.fiscal_provincial as pipeline

    cursor, connection, archive = _use_fakes(monkeypatch)

    pipeline.load([_row()], dry_run=False, raw_members=RAW_MEMBERS)

    assert archive.calls[0][1] == RAW_MEMBERS
    running = _calls(cursor, "VALUES (%s, %s, 'running'")
    assert running and running[0][1] == (
        20,
        60,
        '["worldbank/fiscal-dashboard/provincial.json"]',
    )
    success = _calls(cursor, "UPDATE ingestion_log SET status = 'success'")
    assert success and success[0][1] == (1, 1, 70)
    assert connection.commits >= 3


def test_a_noop_rerun_still_records_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import ingestion.worldbank.fiscal_provincial as pipeline

    cursor, _connection, _archive = _use_fakes(
        monkeypatch,
        latest=[(101, 40, 103, "{}", Decimal("1000"))],
    )

    pipeline.load([_row()], dry_run=False, raw_members=RAW_MEMBERS)

    success = _calls(cursor, "VALUES (%s, 'success', now(), %s, 0, 0")
    assert success and success[0][1] == (
        20,
        1,
        '["worldbank/fiscal-dashboard/provincial.json"]',
    )
    assert not _calls(cursor, "INSERT INTO releases")


def test_a_raw_archive_failure_is_logged(monkeypatch: pytest.MonkeyPatch) -> None:
    import ingestion.worldbank.fiscal_provincial as pipeline
    from ingestion.common.raw_lake import RawLakeError

    cursor, connection, _archive = _use_fakes(
        monkeypatch,
        archive_failure=RawLakeError("storage unavailable"),
    )

    with pytest.raises(FiscalLoadError, match="nothing was loaded"):
        pipeline.load([_row()], dry_run=False, raw_members=RAW_MEMBERS)

    failed = _calls(cursor, "VALUES (%s, 'failed', now(), %s, 0")
    assert failed
    assert failed[0][1][0:2] == (20, 1)
    assert "storage unavailable" in failed[0][1][2]
    assert not _calls(cursor, "INSERT INTO releases")
    assert connection.commits == 1


def test_slice_fetch_retains_the_untouched_csv_for_archiving(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ingestion.worldbank.fiscal_provincial as pipeline
    from ingestion.worldbank.fiscal_acquire import SheetPayload

    content = b"Group2,value\nTaxes,100\n"
    payload = SheetPayload(
        sheet="Provincial Revenue",
        view="ProvincialRevenue",
        source_url="https://example.test/provincial.csv",
        content=content,
    )
    monkeypatch.setattr(pipeline, "fetch_sheet", lambda *_args, **_kw: payload)
    monkeypatch.setattr(pipeline.time, "sleep", lambda _seconds: None)
    raw_members: list[tuple[str, bytes, str]] = []

    rows = pipeline._rows(
        object(),
        "Provincial Revenue",
        {"Type1": "Actual"},
        raw_members,
        "provincial-revenue.csv",
    )

    assert rows == [("Taxes", Decimal("100"))]
    assert raw_members == [
        ("provincial-revenue.csv", content, "https://example.test/provincial.csv")
    ]
