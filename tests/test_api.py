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
    SearchHitRow,
    SeriesResult,
    escape_like,
    latest_period_rows,
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


# A census literacy indicator carrying a real Devanagari name — the fixture that
# proves search works in Nepali, not only English (SRCH.S1).
_CENSUS_LITERACY = IndicatorRow(
    code="CENSUS_LITERACY_RATE",
    name_en="Literacy rate (Census 2021)",
    name_ne="साक्षरता दर",
    definition_en="Share of people aged 5+ who can read and write.",
    topic="education",
    unit_code="PCT",
    unit_name="Percent",
    source_concept="Indv08_LiteracyStatus",
    source="National Statistics Office",
    preferred_source="National Statistics Office",
)

# What the fake search ranges over: the indicators above plus a few places.
# (kind, code, name_en, name_ne, detail, unit_code, definition)
_SEARCHABLE: list[tuple[str, str, str, str | None, str, str | None, str | None]] = [
    ("indicator", _GDP.code, _GDP.name_en, _GDP.name_ne, _GDP.topic, _GDP.unit_code,
     _GDP.definition_en),
    ("indicator", _CENSUS_POP.code, _CENSUS_POP.name_en, _CENSUS_POP.name_ne,
     _CENSUS_POP.topic, _CENSUS_POP.unit_code, _CENSUS_POP.definition_en),
    ("indicator", _CENSUS_LITERACY.code, _CENSUS_LITERACY.name_en, _CENSUS_LITERACY.name_ne,
     _CENSUS_LITERACY.topic, _CENSUS_LITERACY.unit_code, _CENSUS_LITERACY.definition_en),
    ("geography", "NP", "Nepal", "नेपाल", "country", None, None),
    ("geography", "NP0321", "Sarlahi", "सर्लाही", "district", None, None),
    ("geography", "NP03", "Bagmati", "बागमती", "province", None, None),
]


def _fake_score(term: str, code: str, name_en: str, name_ne: str | None) -> int:
    """Mirror of the SQL CASE ladder in PostgresRepository.search."""
    t = term.lower()
    ne = (name_ne or "").lower()
    if code.lower() == t:
        return 100
    if t in code.lower():
        return 80
    if name_en.lower().startswith(t) or (ne and ne.startswith(t)):
        return 60
    if t in name_en.lower() or t in ne:
        return 40
    return 20


class FakeRepository:
    def list_indicators(self) -> list[IndicatorRow]:
        return [_GDP, _CENSUS_POP, _WB_POP, _CENSUS_LITERACY]

    def search(self, term: str, limit: int = 20) -> list[SearchHitRow]:
        """Literal (non-wildcard) case-insensitive substring match.

        Treating the term as literal text is exactly what `escape_like` buys in
        the real query, so a `%` typed by a user finds only rows containing a
        literal percent sign. The escaping logic itself is unit-tested directly
        against `escape_like`; this fake covers the route's behaviour.
        """
        t = term.lower()
        hits = []
        for kind, code, name_en, name_ne, detail, unit, definition in _SEARCHABLE:
            haystacks = [code, name_en, name_ne or "", definition or ""]
            if any(t in h.lower() for h in haystacks):
                hits.append(
                    SearchHitRow(
                        kind=kind, code=code, name_en=name_en, name_ne=name_ne,
                        detail=detail, unit_code=unit,
                        score=_fake_score(term, code, name_en, name_ne),
                    )
                )
        hits.sort(key=lambda h: (-h.score, h.name_en))
        return hits[:limit]

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

    def get_geo_values(
        self, indicator_code: str, level: str, parent_code: str | None = None
    ) -> GeoValuesResult | None:
        if indicator_code != "CENSUS_POP_TOTAL":
            return None
        if level == "province" and parent_code is None:
            values = [
                GeoValueRow("NP01", "Koshi", "कोशी", Decimal("4961412")),
                GeoValueRow("NP03", "Bagmati", "बागमती", Decimal("6116866")),
            ]
        elif level == "local_unit" and parent_code == "NP0327":
            # drill: local units of one district (parent = district P-code)
            values = [
                GeoValueRow("NP0327301", "Kathmandu", None, Decimal("862400")),
                GeoValueRow("NP0327402", "Kirtipur", None, Decimal("67000")),
            ]
        else:
            return None
        return GeoValuesResult(
            indicator_code="CENSUS_POP_TOTAL",
            indicator_name="Population (Census 2021)",
            level=level,
            period="2021",
            unit_code="PERSONS",
            unit_name="Persons",
            source_name="National Statistics Office",
            dataset_name="National Population and Housing Census 2021",
            license=None,
            latest_release_date="2026-07-19",
            values=values,
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


def test_search_matches_english_name_case_insensitively(client: TestClient) -> None:
    res = client.get("/v1/search", params={"q": "literacy"})
    assert res.status_code == 200
    body = res.json()
    assert body["query"] == "literacy"
    codes = [r["code"] for r in body["results"]]
    assert "CENSUS_LITERACY_RATE" in codes
    # Same query in a different case must find the same row.
    assert client.get("/v1/search", params={"q": "LITERACY"}).json()["results"] == body["results"]


def test_search_matches_nepali_devanagari_name(client: TestClient) -> None:
    # The reason the query uses ILIKE and not to_tsvector: an 'english' text
    # search config cannot index Devanagari, which would make name_ne dead text.
    res = client.get("/v1/search", params={"q": "साक्षरता"})
    assert res.status_code == 200
    codes = [r["code"] for r in res.json()["results"]]
    assert "CENSUS_LITERACY_RATE" in codes


def test_search_finds_a_place_and_labels_its_kind(client: TestClient) -> None:
    res = client.get("/v1/search", params={"q": "Sarlahi"})
    hits = res.json()["results"]
    assert [h["code"] for h in hits] == ["NP0321"]
    assert hits[0]["kind"] == "geography"
    assert hits[0]["detail"] == "district"
    assert hits[0]["name_ne"] == "सर्लाही"
    assert hits[0]["unit"] is None


def test_search_ranks_an_exact_code_first(client: TestClient) -> None:
    res = client.get("/v1/search", params={"q": "GDP_GROWTH"})
    results = res.json()["results"]
    assert results[0]["code"] == "GDP_GROWTH"


def test_search_treats_wildcards_as_literal_text(client: TestClient) -> None:
    # Regression guard for the LIKE-injection bug: unescaped, '%%' is a wildcard
    # pair that would match and dump the entire catalogue. Escaped, it is two
    # literal percent signs, which nothing in the corpus contains.
    res = client.get("/v1/search", params={"q": "%%"})
    assert res.status_code == 200
    assert res.json()["total"] == 0


def test_escape_like_neutralises_wildcards() -> None:
    # Backslash must be escaped FIRST, else it double-escapes what follows.
    assert escape_like("100%") == "100\\%"
    assert escape_like("a_b") == "a\\_b"
    assert escape_like("c:\\x") == "c:\\\\x"
    assert escape_like("literacy") == "literacy"


def test_search_rejects_a_too_short_query(client: TestClient) -> None:
    res = client.get("/v1/search", params={"q": "a"})
    assert res.status_code == 422
    # Whitespace is trimmed before the length check, so "  " is too short too.
    assert client.get("/v1/search", params={"q": "   "}).status_code == 422


def test_search_with_no_match_is_empty_not_404(client: TestClient) -> None:
    # "We don't have that" is a real answer from a data portal, not an error.
    res = client.get("/v1/search", params={"q": "zzzznothing"})
    assert res.status_code == 200
    assert res.json() == {"query": "zzzznothing", "total": 0, "results": []}


def test_search_respects_and_bounds_the_limit(client: TestClient) -> None:
    res = client.get("/v1/search", params={"q": "NP", "limit": 1})
    assert res.json()["total"] == 1
    assert client.get("/v1/search", params={"q": "NP", "limit": 51}).status_code == 422
    assert client.get("/v1/search", params={"q": "NP", "limit": 0}).status_code == 422


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


def test_geo_data_drills_to_a_districts_local_units(client: TestClient) -> None:
    """P2B.S8b: level=local_unit with parent=<district> returns just that
    district's municipalities (drill-down)."""
    resp = client.get(
        "/v1/data/geo",
        params={"indicator": "CENSUS_POP_TOTAL", "level": "local_unit", "parent": "NP0327"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["level"] == "local_unit"
    codes = [v["geo_code"] for v in body["values"]]
    assert codes == ["NP0327301", "NP0327402"]


def test_geo_data_local_unit_without_parent_404s_in_fake(client: TestClient) -> None:
    # The fake only serves the NP0327 drill; a bad parent yields an honest 404.
    resp = client.get(
        "/v1/data/geo",
        params={"indicator": "CENSUS_POP_TOTAL", "level": "local_unit", "parent": "NP9999"},
    )
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


# --- latest_period_rows: one year on the map, not all of them -----------------
# The query behind /v1/data/geo returns every year each geography has, because
# is_latest marks the newest RELEASE of a cell, not the newest year. These rows
# are shaped like that query's output; only index 12 (sort_key) matters here.


def _geo_row(code: str, value: str, label: str, sort_key: int) -> tuple[object, ...]:
    return (
        code, code, None, Decimal(value), label, "Provincial expenditure (budget)",
        "NPR_MILLION", "Nepali rupees (millions)", "World Bank",
        "Nepal Fiscal Dashboard", None, "2026-08-06", sort_key,
    )


def test_latest_period_rows_keeps_only_the_newest_year() -> None:
    # The real bug: five fiscal years per province came back as one map.
    rows = [
        _geo_row("NP01", "42120.41", "FY 2019/20", 2019),
        _geo_row("NP01", "36233.53", "FY 2023/24", 2023),
        _geo_row("NP03", "58000.00", "FY 2019/20", 2019),
        _geo_row("NP03", "62209.10", "FY 2023/24", 2023),
    ]
    kept = latest_period_rows(rows)
    assert [r[0] for r in kept] == ["NP01", "NP03"]
    assert {r[4] for r in kept} == {"FY 2023/24"}
    assert [r[3] for r in kept] == [Decimal("36233.53"), Decimal("62209.10")]


def test_latest_period_rows_uses_sort_key_not_the_label() -> None:
    # Label ordering is a trap: 'FY 2019/20' sorts after 'FY 2023/24' in some
    # spellings, so the newest period is decided by sort_key alone.
    rows = [
        _geo_row("NP01", "1", "FY 2023/24", 2023),
        _geo_row("NP01", "2", "FY 2019/20", 2019),
    ]
    assert [r[4] for r in latest_period_rows(rows)] == ["FY 2023/24"]


def test_latest_period_rows_drops_a_geography_missing_that_year() -> None:
    # Blank on the map beats back-filling an older year into the same picture.
    rows = [
        _geo_row("NP01", "10", "FY 2023/24", 2023),
        _geo_row("NP02", "20", "FY 2019/20", 2019),
    ]
    assert [r[0] for r in latest_period_rows(rows)] == ["NP01"]


def test_latest_period_rows_handles_an_empty_result() -> None:
    assert latest_period_rows([]) == []


def test_latest_period_rows_leaves_single_year_data_untouched() -> None:
    # Census data is one period; the helper must not change what already worked.
    rows = [_geo_row("NP01", "4961412", "2021", 2021), _geo_row("NP03", "6116866", "2021", 2021)]
    assert len(latest_period_rows(rows)) == 2
