"""Nepal Data Portal — read-only public API (P1.S10, Master Prompt §3.5).

Versioned from day one (all routes under /v1/). Every data response includes the
numbers AND their provenance. There are no write endpoints. Interactive docs are
auto-generated at /docs.
"""

from __future__ import annotations

import os
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from api.models import (
    DataResponse,
    GeoDataResponse,
    GeoValue,
    IndicatorDetail,
    IndicatorSummary,
    Observation,
    Provenance,
)
from api.repository import PostgresRepository, Repository

app = FastAPI(
    title="Nepal Data Portal API",
    version="1.0.0",
    description="Read-only access to harmonized data about Nepal, with provenance.",
)

# Which browser origins may call this API. Defaults to the local Next.js dev
# server (P1.S11); in deployment, set CORS_ALLOW_ORIGINS to the site's origin(s),
# comma-separated, or "*" — this is a public, read-only API with no credentials,
# so a wildcard is acceptable for open review.
_DEFAULT_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"
_cors_origins = [
    o.strip()
    for o in os.environ.get("CORS_ALLOW_ORIGINS", _DEFAULT_ORIGINS).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def get_repository() -> Repository:
    """Provide the production repository. Overridden in tests with a fake."""
    load_dotenv()
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        raise RuntimeError("DATABASE_URL is not set")
    return PostgresRepository(dsn)


@app.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    """Liveness probe — deliberately does NOT touch the database.

    Render's health check pings this to decide whether the service is up. It must
    stay DB-free: if it queried Postgres, a transient database blip (or a wrong
    DATABASE_URL) would be retried every few seconds, which both fails the whole
    deploy and can trip Supabase's 'too many authentication failures' circuit
    breaker — temporarily blocking even valid connections. Readiness of the data
    is proven by the /v1 endpoints, not by liveness.
    """
    return {"status": "ok"}


@app.get("/v1/indicators", response_model=list[IndicatorSummary])
def list_indicators(
    repo: Annotated[Repository, Depends(get_repository)],
) -> list[IndicatorSummary]:
    return [
        IndicatorSummary(code=r.code, name=r.name_en, topic=r.topic, unit=r.unit_code)
        for r in repo.list_indicators()
    ]


@app.get("/v1/indicators/{code}", response_model=IndicatorDetail)
def get_indicator(
    code: str, repo: Annotated[Repository, Depends(get_repository)]
) -> IndicatorDetail:
    row = repo.get_indicator(code)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown indicator code: {code}")
    return IndicatorDetail(
        code=row.code,
        name_en=row.name_en,
        name_ne=row.name_ne,
        definition_en=row.definition_en,
        topic=row.topic,
        unit_code=row.unit_code,
        unit_name=row.unit_name,
        source_concept=row.source_concept,
    )


@app.get("/v1/data/geo", response_model=GeoDataResponse)
def get_geo_data(
    repo: Annotated[Repository, Depends(get_repository)],
    indicator: Annotated[str, Query(description="Indicator code, e.g. CENSUS_POP_TOTAL")],
    level: Annotated[str, Query(description="Geography level: province or district")],
) -> GeoDataResponse:
    """Latest value of one indicator for EVERY geography at a level — the
    single call a choropleth map needs."""
    if level not in ("province", "district"):
        raise HTTPException(
            status_code=422, detail="level must be 'province' or 'district'"
        )
    indicator_row = repo.get_indicator(indicator)
    if indicator_row is None:
        raise HTTPException(status_code=404, detail=f"Unknown indicator code: {indicator}")
    result = repo.get_geo_values(indicator, level)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No {level}-level data for indicator '{indicator}'",
        )
    return GeoDataResponse(
        indicator=IndicatorSummary(
            code=indicator_row.code, name=indicator_row.name_en,
            topic=indicator_row.topic, unit=indicator_row.unit_code,
        ),
        level=result.level,
        period=result.period,
        unit_code=result.unit_code,
        unit_name=result.unit_name,
        provenance=Provenance(
            source=result.source_name,
            dataset=result.dataset_name,
            license=result.license,
            latest_release_date=result.latest_release_date,
        ),
        values=[
            GeoValue(geo_code=v.geo_code, name=v.name_en, name_ne=v.name_ne, value=float(v.value))
            for v in result.values
        ],
    )


@app.get("/v1/data", response_model=DataResponse)
def get_data(
    repo: Annotated[Repository, Depends(get_repository)],
    indicator: Annotated[str, Query(description="Indicator code, e.g. GDP_GROWTH")],
    geo: Annotated[str, Query(description="Geography code, e.g. NP")] = "NP",
) -> DataResponse:
    indicator_row = repo.get_indicator(indicator)
    if indicator_row is None:
        raise HTTPException(status_code=404, detail=f"Unknown indicator code: {indicator}")
    series = repo.get_series(indicator, geo)
    if series is None:
        raise HTTPException(
            status_code=404, detail=f"No data for indicator '{indicator}' in geography '{geo}'"
        )
    return DataResponse(
        indicator=IndicatorSummary(
            code=indicator_row.code, name=indicator_row.name_en,
            topic=indicator_row.topic, unit=indicator_row.unit_code,
        ),
        geography_code=series.geography_code,
        geography_name=series.geography_name,
        unit_code=series.unit_code,
        unit_name=series.unit_name,
        provenance=Provenance(
            source=series.source_name,
            dataset=series.dataset_name,
            license=series.license,
            latest_release_date=series.latest_release_date,
        ),
        observations=[
            Observation(
                period=o.period, value=float(o.value), status=o.status,
                footnote=o.footnote, release_date=o.release_date,
                breakdowns=o.breakdowns,
            )
            for o in series.observations
        ],
    )
