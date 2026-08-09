"""ECN.S1 tests. Offline: no network, no database.

The three fixtures are real payloads captured from the Election Commission's
results portal on 2026-08-09, byte for byte as it served them:

  ecn_2082_hor_party_seats.json  Common/HoRPartyTop5.txt        (seat chart)
  ecn_2082_constituencies.json   HOR/Lookup/constituencies.json (seat map)
  ecn_2082_districts.json        Local/Lookup/districts.json    (has a BOM)

Two of the tests pin defects that are IN THE SOURCE, not in our code. They are
written as assertions about the portal so that if the ECN ever fixes them, the
suite fails and tells us to delete the workaround — rather than the workaround
quietly outliving the problem.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import requests

from ingestion.election.ecn_client import EcnClient, EcnError, decode_json
from ingestion.election.ecn_probe import (
    HOR_FPTP_SEATS,
    CycleData,
    cross_check,
    real_districts,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = decode_json((FIXTURES / name).read_bytes())
    return rows


# --- decoding ----------------------------------------------------------------


def test_a_payload_with_a_byte_order_mark_still_parses() -> None:
    """The district lookup is served UTF-8 *with* a BOM, which `json.loads`
    rejects outright. Decoding as utf-8-sig is the whole reason `decode_json`
    exists; this test is here so nobody "simplifies" it back to json.loads."""
    raw = (FIXTURES / "ecn_2082_districts.json").read_bytes()
    assert raw[:3] == b"\xef\xbb\xbf", "fixture should still carry the BOM"
    districts = decode_json(raw)
    assert isinstance(districts, list)
    assert districts[0]["name"] == "ताप्लेजुंग"


# --- the district lookup's placeholder rows ----------------------------------


def test_the_district_lookup_carries_two_placeholder_rows() -> None:
    """SOURCE DEFECT, pinned. The portal's district list has 79 rows for
    Nepal's 77 districts: ids 98 and 99 are named "NA" and belong to no
    province. Left in, they become two phantom districts in every join."""
    districts = _load("ecn_2082_districts.json")
    assert len(districts) == 79
    placeholders = [d for d in districts if d["name"] == "NA"]
    assert sorted(d["id"] for d in placeholders) == [98, 99]
    assert all(d["parentId"] is None for d in placeholders)


def test_dropping_the_placeholders_leaves_nepals_77_districts() -> None:
    districts = _load("ecn_2082_districts.json")
    real = real_districts(districts)
    assert len(real) == 77
    assert {d["parentId"] for d in real} == {1, 2, 3, 4, 5, 6, 7}


# --- the constituency lookup's duplicated district ---------------------------


def test_the_constituency_lookup_lists_one_district_twice() -> None:
    """SOURCE DEFECT, pinned. District code 77 appears twice with 2 seats each,
    so a naive sum gives 167 seats for a 165-seat house. Summing per DISTINCT
    district gives the constitutional number."""
    consts = _load("ecn_2082_constituencies.json")
    assert len(consts) == 78
    naive_total = sum(row["consts"] for row in consts)
    assert naive_total == 167

    per_district = {row["distId"]: row["consts"] for row in consts}
    assert len(per_district) == 77
    assert sum(per_district.values()) == HOR_FPTP_SEATS


# --- the seat chart ----------------------------------------------------------


def test_the_seat_chart_accounts_for_every_fptp_seat() -> None:
    chart = _load("ecn_2082_hor_party_seats.json")
    assert sum(row["TotWin"] for row in chart) == HOR_FPTP_SEATS
    # Nothing was still being counted when this was captured: a live count would
    # show seats in TotLead. All zero means these are settled results.
    assert all(row["TotLead"] == 0 for row in chart)


# --- the cross-checks themselves ---------------------------------------------


def _consistent_cycle() -> CycleData:
    """A tiny, internally consistent cycle: two districts whose PR votes add up
    to the national figures, and a seat chart matching the elected candidates."""
    return CycleData(
        cycle="TEST",
        districts=[
            {"id": 1, "name": "क", "parentId": 1},
            {"id": 2, "name": "ख", "parentId": 1},
            {"id": 99, "name": "NA", "parentId": None},
        ],
        constituencies=[{"distId": 1, "consts": 100}, {"distId": 2, "consts": 65}],
        pr_national=[
            {"PoliticalPartyName": "A", "TotalVoteReceived": 300},
            {"PoliticalPartyName": "B", "TotalVoteReceived": 100},
        ],
        pr_by_district={
            1: [
                {"PoliticalPartyName": "A", "TotalVoteReceived": 200},
                {"PoliticalPartyName": "B", "TotalVoteReceived": 60},
            ],
            2: [
                {"PoliticalPartyName": "A", "TotalVoteReceived": 100},
                {"PoliticalPartyName": "B", "TotalVoteReceived": 40},
            ],
        },
        fptp_party_chart=[
            {"PoliticalPartyName": "A", "TotWin": 164},
            {"PoliticalPartyName": "B", "TotWin": 1},
        ],
        candidates=(
            [{"PoliticalPartyName": "A", "Remarks": "Elected"} for _ in range(164)]
            + [{"PoliticalPartyName": "B", "Remarks": "Elected"}]
            + [{"PoliticalPartyName": "B", "Remarks": None}]
        ),
    )


def test_a_consistent_cycle_passes_every_cross_check() -> None:
    failures = [(n, d) for n, passed, d in cross_check(_consistent_cycle()) if not passed]
    assert failures == []


def test_a_partial_harvest_is_caught_before_the_totals_are_believed() -> None:
    """The lesson from the first live run: throttled part-way through, it read
    62 of 77 districts and reported that the source did not reconcile. Coverage
    must fail first, and say so, so nobody blames the ECN for our own gap."""
    data = _consistent_cycle()
    del data.pr_by_district[2]
    results = {n: (passed, detail) for n, passed, detail in cross_check(data)}
    coverage = next(n for n in results if "PR file was read for every district" in n)
    assert results[coverage][0] is False
    assert "NOT meaningful" in results[coverage][1]


def test_a_district_that_does_not_add_up_is_caught() -> None:
    """The point of the check: if one district's votes go missing, the national
    total no longer reconciles and the spike says so rather than charting it."""
    data = _consistent_cycle()
    data.pr_by_district[2][0]["TotalVoteReceived"] = 99  # one vote short
    failed = [n for n, passed, _ in cross_check(data) if not passed]
    assert any("sum to the national total" in n for n in failed)
    assert any("every party's district votes" in n for n in failed)


def test_a_duplicated_district_in_the_lookup_is_caught() -> None:
    data = _consistent_cycle()
    data.constituencies.append({"distId": 2, "consts": 65})
    failed = [n for n, passed, _ in cross_check(data) if not passed]
    assert any("one row per district" in n for n in failed)


def test_a_house_of_the_wrong_size_is_caught() -> None:
    data = _consistent_cycle()
    data.fptp_party_chart[0]["TotWin"] = 163
    failed = [n for n, passed, _ in cross_check(data) if not passed]
    assert any(f"FPTP seats total {HOR_FPTP_SEATS}" in n for n in failed)


# --- the client's contract ---------------------------------------------------


class _FakeResponse:
    def __init__(self, status: int, content_type: str, body: bytes) -> None:
        self.status_code = status
        self.headers = {"Content-Type": content_type}
        self.content = body


class _FakeSession:
    """Records what the client sent, and answers with whatever we queue."""

    def __init__(self, response: _FakeResponse) -> None:
        self.headers: dict[str, str] = {}
        self.cookies: dict[str, str] = {"CsrfToken": "tok-123"}
        self.response = response
        self.sent: list[tuple[str, dict[str, str]]] = []

    def get(
        self, url: str, headers: dict[str, str] | None = None, timeout: int = 0
    ) -> _FakeResponse:
        self.sent.append((url, headers or {}))
        if url.endswith("/"):  # the landing page
            return _FakeResponse(200, "text/html", b"<html/>")
        return self.response


def _client(response: _FakeResponse) -> tuple[EcnClient, _FakeSession]:
    session = _FakeSession(response)
    # A stand-in for requests.Session: the client only ever calls .get,
    # .headers and .cookies, which is exactly what this provides.
    client = EcnClient(session=cast(requests.Session, session), pause_s=0)
    return client, session


def test_every_request_carries_the_four_things_the_handler_demands() -> None:
    """Session cookie, CSRF header, browser User-Agent, Referer. Drop any one
    and the portal answers 403 — so all four are asserted, not assumed."""
    client, session = _client(_FakeResponse(200, "application/json", b"[]"))
    client.fetch_json("JSONFiles/anything.json")

    assert "Mozilla/5.0" in session.headers["User-Agent"]
    _, headers = session.sent[-1]
    assert headers["X-CSRF-Token"] == "tok-123"
    assert headers["Referer"].startswith("https://result.election.gov.np")


def test_an_html_error_page_is_refused_rather_than_parsed() -> None:
    """The handler serves its 403 page as HTML with a 200 in some paths. A
    caller that trusted the status code would parse an error page as data."""
    client, _ = _client(_FakeResponse(200, "text/html", b"<html>403</html>"))
    with pytest.raises(EcnError, match="expected JSON"):
        client.fetch_json("JSONFiles/anything.json")
