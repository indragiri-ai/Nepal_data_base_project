"""The API's server-side limits (security review 2026-09-06, findings 1 and 9).

Two things are being pinned here, and the second matters as much as the first:

1. An oversized or malformed request is refused, with an answer that says what
   to do about it.
2. The caps are still ABOVE the real shape of Nepal's data. A cap set below it
   does not look like a bug — the map simply loses municipalities, or a chart
   quietly stops at an arbitrary date. The numbers in `api/policy.py` were
   measured against the live warehouse; these tests fail if someone tightens
   them past what the portal itself asks for.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import database
from api.access import AccessGuard, AccessMiddleware
from api.policy import (
    MAX_BREAKDOWN_ROWS,
    MAX_GEO_ROWS,
    MAX_INDICATOR_ROWS,
    MAX_RESPONSE_BYTES,
    MAX_ROWS,
    MAX_WINDOW_DAYS,
    QueryTooBroad,
    bounded,
    validate_window,
)

# What the warehouse actually holds, counted 2026-09-07. Update these with the
# measurement, not with a guess, when the data grows.
LOCAL_UNITS = 753
WIDEST_SERIES = 4_675  # KALIMATI_PRICE_AVG, Cauli Local, daily since 2013
WIDEST_BREAKDOWN = 6_777  # CENSUS_HH_DRINKING_WATER by local unit
INDICATORS_WITH_DATA = 1_496


# --- the caps must clear the real data --------------------------------------


def test_caps_clear_the_widest_real_map() -> None:
    """A 100-row cap would have served 100 of Nepal's 753 municipalities."""
    assert MAX_GEO_ROWS > LOCAL_UNITS
    assert MAX_BREAKDOWN_ROWS > WIDEST_BREAKDOWN


def test_caps_clear_the_longest_real_series() -> None:
    """Thirteen years of daily vegetable prices is one honest chart."""
    assert MAX_ROWS > WIDEST_SERIES


def test_caps_clear_the_catalogue() -> None:
    assert MAX_INDICATOR_ROWS > INDICATORS_WITH_DATA


def test_the_response_cap_still_fits_the_longest_series() -> None:
    """~140 bytes per observation, measured in the review's 76,747-row probe."""
    assert MAX_RESPONSE_BYTES > WIDEST_SERIES * 140


# --- bounded() ---------------------------------------------------------------


def test_bounded_passes_a_result_at_the_cap() -> None:
    rows = list(range(10))
    assert bounded(rows, 10) == rows


def test_bounded_refuses_one_row_past_the_cap_and_says_what_to_do() -> None:
    with pytest.raises(QueryTooBroad) as raised:
        bounded(list(range(11)), 10)
    message = str(raised.value)
    assert "10" in message
    assert "breakdown" in message and "date range" in message


# --- validate_window ---------------------------------------------------------


def test_a_half_given_breakdown_is_refused() -> None:
    with pytest.raises(QueryTooBroad):
        validate_window("commodity", None, None, None)


def test_a_half_given_window_is_refused() -> None:
    with pytest.raises(QueryTooBroad):
        validate_window(None, None, date(2020, 1, 1), None)


def test_a_backwards_window_is_refused() -> None:
    with pytest.raises(QueryTooBroad):
        validate_window(None, None, date(2020, 1, 2), date(2020, 1, 1))


def test_an_absurd_window_is_refused_but_a_century_is_not() -> None:
    start = date(1900, 1, 1)
    validate_window(None, None, start, start + timedelta(days=MAX_WINDOW_DAYS - 1))
    with pytest.raises(QueryTooBroad):
        validate_window(None, None, start, date(2900, 1, 1))


def test_no_filters_at_all_is_allowed_here() -> None:
    """Breadth is bounded by `bounded()`, not by demanding filters up front: a
    short series with no breakdown is the common, legitimate case."""
    validate_window(None, None, None, None)


# --- the middleware, on a tiny app of its own --------------------------------


def _app(payload: bytes = b'{"ok": true}') -> FastAPI:
    app = FastAPI()
    app.add_middleware(AccessMiddleware)

    @app.get("/v1/thing")
    def thing() -> object:  # pragma: no cover - exercised through the client
        return {"body": payload.decode()}

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:  # pragma: no cover - exercised through the client
        return {"status": "ok"}

    return app


def test_a_normal_request_passes_and_is_marked_uncacheable() -> None:
    client = TestClient(_app())
    resp = client.get("/v1/thing")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-store"
    assert resp.headers["x-content-type-options"] == "nosniff"


def test_an_oversized_answer_is_refused_rather_than_sent() -> None:
    client = TestClient(_app(b"x" * (MAX_RESPONSE_BYTES + 1)))
    resp = client.get("/v1/thing")
    assert resp.status_code == 413
    assert "narrow" in resp.json()["detail"].lower()


def test_a_repeated_parameter_is_refused() -> None:
    client = TestClient(_app())
    assert client.get("/v1/thing?geo=NP&geo=NP01").status_code == 422


def test_codes_may_repeat_because_one_page_asks_for_many_indicators() -> None:
    client = TestClient(_app())
    assert client.get("/v1/thing?codes=A&codes=B").status_code == 200


def test_an_absurdly_long_query_is_refused() -> None:
    client = TestClient(_app())
    assert client.get("/v1/thing?q=" + "x" * 5000).status_code == 414


def test_health_is_not_metered() -> None:
    """The keep-alive ping must not consume a data allowance."""
    client = TestClient(_app())
    assert client.get("/health").status_code == 200


# --- the allowance, when an operator has configured one ----------------------


class FakeGuard:
    """Stands in for `api_private`: the same two calls, no database."""

    def __init__(self, allow: bool = True) -> None:
        self.allow = allow
        self.settled: list[int] = []

    def reserve(self, client: str) -> tuple[str | None, int]:
        return ("lease-1" if self.allow else None, 0 if self.allow else 7)

    def finish(self, lease: str, size: int) -> None:
        self.settled.append(size)


def _metered(guard: AccessGuard, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # The allowance is keyed by a hashed caller address, so it stays off until
    # an operator supplies the salt.
    monkeypatch.setenv("API_CLIENT_HASH_KEY", "k" * 32)
    app = _app()
    app.state.access_guard = guard
    return TestClient(app, client=("203.0.113.7", 3000))


def test_a_refused_allowance_answers_429_with_when_to_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resp = _metered(FakeGuard(allow=False), monkeypatch).get("/v1/thing")
    assert resp.status_code == 429
    assert resp.headers["retry-after"] == "7"


def test_an_allowed_request_settles_the_bytes_it_actually_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard = FakeGuard()
    resp = _metered(guard, monkeypatch).get("/v1/thing")
    assert resp.status_code == 200
    assert guard.settled == [len(resp.content)]


# --- how the API connects -----------------------------------------------------


def test_tls_only_verifies_when_there_is_a_certificate_to_verify_against(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The failure this pins: `verify-full` with no pinned CA does not fall
    back to encryption, it refuses every connection — Supabase signs its pooler
    with its own private CA, so no public bundle can check it. Verified against
    the live database on 2026-09-07.
    """
    monkeypatch.delenv("API_SSL_MODE", raising=False)
    monkeypatch.delenv("API_SSL_ROOT_CERT", raising=False)
    monkeypatch.setattr(database, "PINNED_CA_PATH", tmp_path / "absent.crt")
    assert database.tls_settings() == ("require", None)

    ca = tmp_path / "prod-ca-2021.crt"
    ca.write_text("-- not a real certificate --")
    monkeypatch.setattr(database, "PINNED_CA_PATH", ca)
    assert database.tls_settings() == ("verify-full", str(ca))


def test_a_root_certificate_is_never_supplied_without_verification(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """libpq treats `require` PLUS a root certificate as verify-ca, so handing
    it a public bundle "just in case" breaks every Supabase connection."""
    monkeypatch.delenv("API_SSL_MODE", raising=False)
    monkeypatch.delenv("API_SSL_ROOT_CERT", raising=False)
    monkeypatch.setattr(database, "PINNED_CA_PATH", tmp_path / "absent.crt")
    mode, root = database.tls_settings()
    assert mode == "require"
    assert root is None


def test_an_operator_can_override_the_tls_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("API_SSL_MODE", "disable")
    monkeypatch.setattr(database, "PINNED_CA_PATH", tmp_path / "absent.crt")
    assert database.tls_settings()[0] == "disable"


def test_the_api_falls_back_to_the_admin_dsn_rather_than_refusing_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A portal that will not start is worse than one running as it always has."""
    monkeypatch.delenv("API_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgres://postgres:pw@example.invalid:5432/postgres")
    assert database.serving_dsn().startswith("postgres://postgres:")


def test_a_serving_dsn_that_is_not_the_restricted_role_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Naming API_DATABASE_URL is a claim that it is the read-only role; a
    typo that leaves the admin credential in place must not pass silently."""
    monkeypatch.setenv(
        "API_DATABASE_URL", "postgres://postgres:pw@example.invalid:5432/postgres"
    )
    with pytest.raises(RuntimeError, match="portal_api"):
        database.serving_dsn()


def test_the_supabase_pooler_role_suffix_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Supabase's pooler appends the project reference to the role name."""
    monkeypatch.setenv(
        "API_DATABASE_URL", "postgres://portal_api.abc123:pw@pooler.example:5432/postgres"
    )
    assert "portal_api.abc123" in database.serving_dsn()


def test_the_allowance_is_off_until_it_is_configured() -> None:
    """No key, no database calls: the portal serves as it always has, and the
    always-on protections above still apply."""
    from api.access import quota_configured

    assert not quota_configured()
    assert TestClient(_app()).get("/v1/thing").status_code == 200
