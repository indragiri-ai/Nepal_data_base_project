"""API tests (P1.S10). Run offline: a fake repository is injected so no DB is hit."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.main import app, get_repository
from api.repository import IndicatorRow, ObservationRow, SeriesResult

_GDP = IndicatorRow(
    code="GDP_GROWTH",
    name_en="GDP growth (annual %)",
    name_ne=None,
    definition_en="Annual percentage growth rate of GDP.",
    topic="economy",
    unit_code="PCT",
    unit_name="Percent",
    source_concept="NY.GDP.MKTP.KD.ZG",
)


class FakeRepository:
    def list_indicators(self) -> list[IndicatorRow]:
        return [_GDP]

    def get_indicator(self, code: str) -> IndicatorRow | None:
        return _GDP if code == "GDP_GROWTH" else None

    def get_series(self, indicator_code: str, geography_code: str) -> SeriesResult | None:
        if indicator_code != "GDP_GROWTH" or geography_code != "NP":
            return None
        return SeriesResult(
            indicator_code="GDP_GROWTH",
            indicator_name="GDP growth (annual %)",
            geography_code="NP",
            geography_name="Nepal",
            unit_code="PCT",
            unit_name="Percent",
            source_name="World Bank",
            dataset_name="World Development Indicators",
            license="CC BY 4.0",
            latest_release_date="2026-06-13",
            observations=[
                ObservationRow("2019", 2019, Decimal("6.66"), "final", None, "2026-06-13"),
                ObservationRow("2020", 2020, Decimal("-2.37"), "final", None, "2026-06-13"),
            ],
        )


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.dependency_overrides[get_repository] = FakeRepository
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_list_indicators(client: TestClient) -> None:
    resp = client.get("/v1/indicators")
    assert resp.status_code == 200
    codes = [item["code"] for item in resp.json()]
    assert "GDP_GROWTH" in codes


def test_get_data_includes_provenance(client: TestClient) -> None:
    resp = client.get("/v1/data", params={"indicator": "GDP_GROWTH", "geo": "NP"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["provenance"]["source"] == "World Bank"
    assert body["unit_code"] == "PCT"
    assert len(body["observations"]) == 2
    assert body["observations"][1]["value"] == -2.37  # 2020 COVID contraction


def test_unknown_indicator_returns_clean_404(client: TestClient) -> None:
    resp = client.get("/v1/indicators/NOPE")
    assert resp.status_code == 404
    assert "Unknown indicator" in resp.json()["detail"]


def test_data_for_unknown_indicator_returns_404(client: TestClient) -> None:
    resp = client.get("/v1/data", params={"indicator": "NOPE"})
    assert resp.status_code == 404
