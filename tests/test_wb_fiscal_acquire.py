"""WBF.S1 acquisition tests. Offline by design: a fake session replaces requests."""

from __future__ import annotations

from typing import Any

import pytest

from ingestion.worldbank.fiscal_acquire import (
    DATA_SHEETS,
    NON_DATA_SHEETS,
    FiscalAcquireError,
    SheetPayload,
    describe,
    fetch_sheet,
    view_name,
)

# A real response body, trimmed: the first rows of Federal Revenue as returned
# on 2026-08-01. Kept verbatim so the parser is tested against the source's own
# shape — quoted thousands separators, repeated Year1 column, and all.
FEDERAL_REVENUE_CSV = (
    b"Year1,fed_measure_%tot,Group0,Group1,Group2,Group3,Group4,Type1,Year1\r\n"
    b'FY2018,"766,036.1",Revenue and grants,Revenue and grants,*,*,*,Actual,FY2018\r\n'
    b'FY2019,"765,535.7",Revenue and grants,Revenue and grants,*,*,*,Actual,FY2019\r\n'
)

VIZ_SHELL_HTML = b"<!DOCTYPE html><html><head><title>Tableau</title></head><body></body></html>"


class FakeResponse:
    def __init__(self, content: bytes, content_type: str, url: str = "https://x/y.csv") -> None:
        self.content = content
        self.headers = {"content-type": content_type}
        self.url = url


class FakeSession:
    """Serves a scripted sequence of responses and records the calls made."""

    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, url: str, params: dict[str, Any] | None = None, **_: Any) -> FakeResponse:
        self.calls.append((url, dict(params or {})))
        if not self._responses:
            raise AssertionError("FakeSession ran out of scripted responses")
        return self._responses.pop(0)


def test_view_name_strips_spaces() -> None:
    # Tableau's URL name for "Local Level Revenue" is "LocalLevelRevenue".
    assert view_name("Local Level Revenue") == "LocalLevelRevenue"
    assert view_name("FederalRevenue") == "FederalRevenue"


def test_fetch_sheet_returns_parsed_rows() -> None:
    session = FakeSession([FakeResponse(FEDERAL_REVENUE_CSV, "text/csv")])
    payload = fetch_sheet(session, "Federal Revenue")  # type: ignore[arg-type]

    assert payload.view == "FederalRevenue"
    rows = payload.rows
    assert rows[0][0] == "Year1"
    assert rows[1][0] == "FY2018"
    # The value keeps its source formatting here; parsing to a number is S2's job.
    assert rows[1][1] == "766,036.1"
    assert rows[1][7] == "Actual"


def test_fetch_sheet_sends_embed_flag_and_filters() -> None:
    session = FakeSession([FakeResponse(FEDERAL_REVENUE_CSV, "text/csv")])
    fetch_sheet(session, "Provincial Revenue", {"Fiscal year": "FY2020"})  # type: ignore[arg-type]

    url, params = session.calls[0]
    assert url.endswith("/ProvincialRevenue.csv")
    assert params[":embed"] == "y"
    assert params["Fiscal year"] == "FY2020"


def test_fetch_sheet_retries_once_when_the_session_lapsed() -> None:
    # A shell means the cookie went stale; reloading the view should fix it.
    session = FakeSession([
        FakeResponse(VIZ_SHELL_HTML, "text/html;charset=utf-8"),
        FakeResponse(b"", "text/html"),  # the view reload
        FakeResponse(FEDERAL_REVENUE_CSV, "text/csv"),
    ])
    payload = fetch_sheet(session, "Federal Revenue")  # type: ignore[arg-type]
    assert payload.rows[1][0] == "FY2018"
    assert len(session.calls) == 3


def test_fetch_sheet_fails_loudly_on_a_shell() -> None:
    # Rule 1: an HTML shell parsed as data is silent corruption. It must raise.
    session = FakeSession([
        FakeResponse(VIZ_SHELL_HTML, "text/html;charset=utf-8"),
        FakeResponse(b"", "text/html"),
        FakeResponse(VIZ_SHELL_HTML, "text/html;charset=utf-8"),
    ])
    with pytest.raises(FiscalAcquireError, match="expected text/csv"):
        fetch_sheet(session, "Federal Revenue")  # type: ignore[arg-type]


def test_describe_reports_shape_without_values() -> None:
    payload = SheetPayload(
        sheet="Federal Revenue",
        view="FederalRevenue",
        source_url="https://dataviz.worldbank.org/views/x.csv",
        content=FEDERAL_REVENUE_CSV,
    )
    record = describe(payload)
    assert record["default_view_rows"] == 2
    columns = record["columns"]
    assert isinstance(columns, list)
    assert columns[0] == "Year1"
    # The inventory is a shape record; it must not carry the figures themselves.
    assert "766,036.1" not in str(record)


def test_sheet_inventory_is_the_workbooks_own_list() -> None:
    assert len(DATA_SHEETS) == 16
    assert len(set(DATA_SHEETS)) == 16
    for tier in ("Federal", "Provincial", "Local Level"):
        assert any(s.startswith(tier) for s in DATA_SHEETS), tier
    # Chrome and scratch sheets are excluded deliberately, not forgotten.
    assert set(NON_DATA_SHEETS).isdisjoint(DATA_SHEETS)
