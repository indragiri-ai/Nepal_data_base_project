"""API tests (P1.S10). Run offline: a fake repository is injected so no DB is hit."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.main import app, get_repository
from api.repository import (
    DatasetMetaRow,
    GeoValueRow,
    GeoValuesResult,
    IndicatorRow,
    IndicatorSparkRow,
    ObservationRow,
    SeriesResult,
)

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

_CENSUS_POP = IndicatorRow(
    code="CENSUS_POP_TOTAL",
    name_en="Population (Census 2021)",
    name_ne=None,
    definition_en="Total enumerated population, Census 2021.",
    topic="population",
    unit_code="PERSONS",
    unit_name="Persons",
    source_concept="population/highlight:total|male|female",
    # headline for population: origin == preferred
    source="National Statistics Office",
    preferred_source="National Statistics Office",
)

# The World Bank population series — an ALTERNATIVE to the census (decision 0005):
# its own source differs from the headline (preferred) source.
_WB_POP = IndicatorRow(
    code="POP_TOTAL",
    name_en="Population, total",
    name_ne=None,
    definition_en="Total population (World Bank modeled estimate).",
    topic="population",
    unit_code="PERSONS",
    unit_name="Persons",
    source_concept="SP.POP.TOTL",
    source="World Bank",
    preferred_source="National Statistics Office",
)


class FakeRepository:
    def list_indicators(self) -> list[IndicatorRow]:
        return [_GDP, _CENSUS_POP, _WB_POP]

    def get_spark_series(self) -> list[IndicatorSparkRow]:
        return [
            IndicatorSparkRow(
                code="GDP_GROWTH",
                latest_period="2020",
                latest_value=Decimal("-2.37"),
                points=[Decimal("7.62"), Decimal("6.66"), Decimal("-2.37")],
            ),
            IndicatorSparkRow(
                code="CENSUS_POP_TOTAL",
                latest_period="2021",
                latest_value=Decimal("29164578"),
                points=[Decimal("29164578")],
            ),
        ]

    def get_indicator(self, code: str) -> IndicatorRow | None:
        by_code = {"GDP_GROWTH": _GDP, "CENSUS_POP_TOTAL": _CENSUS_POP, "POP_TOTAL": _WB_POP}
        return by_code.get(code)

    def get_geo_values(self, indicator_code: str, level: str) -> GeoValuesResult | None:
        if indicator_code != "CENSUS_POP_TOTAL" or level != "province":
            return None
        return GeoValuesResult(
            indicator_code="CENSUS_POP_TOTAL",
            indicator_name="Population (Census 2021)",
            level="province",
            period="2021",
            unit_code="PERSONS",
            unit_name="Persons",
            source_name="National Statistics Office",
            dataset_name="National Population and Housing Census 2021",
            license=None,
            latest_release_date="2026-07-19",
            values=[
                GeoValueRow("NP01", "Koshi", "कोशी", Decimal("4961412")),
                GeoValueRow("NP03", "Bagmati", "बागमती", Decimal("6116866")),
            ],
        )

    def get_meta(self) -> list[DatasetMetaRow]:
        return [
            DatasetMetaRow(
                dataset="World Development Indicators",
                source="World Bank",
                last_updated="2026-07-20",
                latest_release_date="2026-07-20",
            ),
            DatasetMetaRow(
                dataset="Banking & Financial Statistics — Monthly",
                source="Nepal Rastra Bank",
                last_updated="2026-07-10",
                latest_release_date="2026-07-10",
            ),
        ]

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


def test_health_is_db_free(client: TestClient) -> None:
    # The health check must return 200 without any repository/DB access, so a
    # DB outage or wrong DATABASE_URL never fails the deploy (see render.yaml).
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_list_indicators(client: TestClient) -> None:
    resp = client.get("/v1/indicators")
    assert resp.status_code == 200
    codes = [item["code"] for item in resp.json()]
    assert "GDP_GROWTH" in codes


def test_list_indicators_exposes_headline_badge_fields(client: TestClient) -> None:
    """/v1/indicators carries source + preferred_source so the frontend can badge
    an alternative estimate (decision 0005)."""
    by_code = {item["code"]: item for item in client.get("/v1/indicators").json()}

    # A headline series: its source is also the preferred (headline) source.
    census = by_code["CENSUS_POP_TOTAL"]
    assert census["source"] == census["preferred_source"] == "National Statistics Office"

    # The World Bank population series is an alternative: source != preferred_source,
    # and the preferred (headline) source is the census.
    wb = by_code["POP_TOTAL"]
    assert wb["source"] == "World Bank"
    assert wb["preferred_source"] == "National Statistics Office"
    assert wb["source"] != wb["preferred_source"]


def test_indicator_sparks(client: TestClient) -> None:
    """/v1/indicators/spark returns latest value + a short trend per indicator,
    and is matched before /v1/indicators/{code} (so 'spark' is not a code)."""
    resp = client.get("/v1/indicators/spark")
    assert resp.status_code == 200
    by_code = {r["code"]: r for r in resp.json()}
    gdp = by_code["GDP_GROWTH"]
    assert gdp["latest_value"] == -2.37
    assert gdp["latest_period"] == "2020"
    assert gdp["points"] == [7.62, 6.66, -2.37]
    # a single-year census fact has a one-point series
    assert by_code["CENSUS_POP_TOTAL"]["points"] == [29164578.0]


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


def test_geo_data_returns_values_for_a_level(client: TestClient) -> None:
    resp = client.get("/v1/data/geo", params={"indicator": "CENSUS_POP_TOTAL", "level": "province"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["level"] == "province"
    assert body["period"] == "2021"
    assert body["provenance"]["source"] == "National Statistics Office"
    codes = {v["geo_code"]: v for v in body["values"]}
    assert codes["NP03"]["value"] == 6116866
    assert codes["NP03"]["name_ne"] == "बागमती"


def test_geo_data_rejects_unknown_level(client: TestClient) -> None:
    resp = client.get("/v1/data/geo", params={"indicator": "CENSUS_POP_TOTAL", "level": "ward"})
    assert resp.status_code == 422


def test_geo_data_404_when_no_data_at_level(client: TestClient) -> None:
    resp = client.get("/v1/data/geo", params={"indicator": "GDP_GROWTH", "level": "district"})
    assert resp.status_code == 404


def test_meta_reports_freshness_per_dataset(client: TestClient) -> None:
    resp = client.get("/v1/meta")
    assert resp.status_code == 200
    body = resp.json()
    # data_updated is the most recent successful ingestion across all datasets.
    assert body["data_updated"] == "2026-07-20"
    datasets = {d["dataset"]: d for d in body["datasets"]}
    assert datasets["World Development Indicators"]["source"] == "World Bank"
    assert datasets["World Development Indicators"]["last_updated"] == "2026-07-20"
    assert "Banking & Financial Statistics — Monthly" in datasets
