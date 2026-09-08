"""Nepal Data Portal — read-only public API (P1.S10, Master Prompt §3.5).

Versioned from day one (all routes under /v1/). Every data response includes the
numbers AND their provenance. There are no write endpoints. Interactive docs are
auto-generated at /docs.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.access import AccessMiddleware
from api.database import serving_dsn
from api.models import (
    DataResponse,
    DatasetMeta,
    GeoBreakdownCell,
    GeoBreakdownResponse,
    GeoDataResponse,
    GeoValue,
    HazardSummary,
    Incident,
    IncidentDetail,
    IncidentsResponse,
    IndicatorDetail,
    IndicatorSpark,
    IndicatorSummary,
    MetaResponse,
    Observation,
    Provenance,
    SearchHit,
    SearchResponse,
    SeasonalityPoint,
    SeasonalityResponse,
)
from api.policy import (
    MAX_SEASONALITY_ROWS,
    MAX_SPARK_CODES,
    QueryTooBroad,
    bounded,
    validate_window,
)
from api.repository import IncidentRow, PostgresRepository, Repository

load_dotenv()

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
app.add_middleware(AccessMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def get_repository() -> Repository:
    """Provide the production repository. Overridden in tests with a fake."""
    load_dotenv()
    return PostgresRepository(serving_dsn())


@app.exception_handler(QueryTooBroad)
async def query_too_broad(_request: object, exc: QueryTooBroad) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


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
        IndicatorSummary(
            code=r.code,
            name=r.name_en,
            topic=r.topic,
            unit=r.unit_code,
            source=r.source,
            preferred_source=r.preferred_source,
        )
        for r in repo.list_indicators()
    ]


@app.get("/v1/indicators/spark", response_model=list[IndicatorSpark])
def list_indicator_sparks(
    repo: Annotated[Repository, Depends(get_repository)],
    codes: Annotated[
        list[str],
        Query(
            min_length=1,
            max_length=MAX_SPARK_CODES,
            description="Indicator codes to draw, repeated: ?codes=GDP_GROWTH&codes=CPI_YOY",
        ),
    ],
) -> list[IndicatorSpark]:
    """The named indicators' latest value + a short recent trend, in one call —
    the data behind the sector-page cards (avoids one request per indicator).
    Declared before /v1/indicators/{code} so 'spark' isn't read as a code.

    The caller must name the codes: asking for every indicator's trend is a
    query over the whole warehouse, which is what the 2026-09-06 review found
    the browser doing on every sector page.
    """
    return [
        IndicatorSpark(
            code=r.code,
            latest_period=r.latest_period,
            latest_value=float(r.latest_value),
            points=[float(p) for p in r.points],
        )
        for r in repo.get_spark_series(list(dict.fromkeys(codes)))
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


@app.get("/v1/meta", response_model=MetaResponse)
def get_meta(repo: Annotated[Repository, Depends(get_repository)]) -> MetaResponse:
    """Data freshness per dataset — when each pipeline last succeeded and its
    latest release date. `data_updated` is the newest of those, for the footer."""
    rows = repo.get_meta()
    updated = [r.last_updated for r in rows if r.last_updated is not None]
    return MetaResponse(
        data_updated=max(updated) if updated else None,
        datasets=[
            DatasetMeta(
                dataset=r.dataset,
                source=r.source,
                last_updated=r.last_updated,
                latest_release_date=r.latest_release_date,
            )
            for r in rows
        ],
    )


_MIN_QUERY_LEN = 2


@app.get("/v1/search", response_model=SearchResponse)
def search(
    repo: Annotated[Repository, Depends(get_repository)],
    q: Annotated[
        str,
        Query(
            description="Free text: an indicator name, a code, or a place."
            " English or Nepali (Devanagari)."
        ),
    ],
    limit: Annotated[int, Query(ge=1, le=50, description="Maximum hits to return.")] = 20,
) -> SearchResponse:
    """Search every indicator and geography in the warehouse from one box.

    Matching is case-insensitive substring in both English and Nepali. A query
    that matches nothing returns an empty list, not a 404 — "we don't have
    that" is a legitimate answer from a data portal and the UI says so plainly.
    """
    term = q.strip()
    if len(term) < _MIN_QUERY_LEN:
        raise HTTPException(
            status_code=422,
            detail=f"Search needs at least {_MIN_QUERY_LEN} characters.",
        )
    hits = repo.search(term, limit)
    return SearchResponse(
        query=term,
        total=len(hits),
        results=[
            SearchHit(
                kind=h.kind,
                code=h.code,
                name=h.name_en,
                name_ne=h.name_ne,
                detail=h.detail,
                unit=h.unit_code,
            )
            for h in hits
        ],
    )


@app.get("/v1/data/geo", response_model=GeoDataResponse)
def get_geo_data(
    repo: Annotated[Repository, Depends(get_repository)],
    indicator: Annotated[str, Query(description="Indicator code, e.g. CENSUS_POP_TOTAL")],
    level: Annotated[str, Query(description="Geography level: province, district, or local_unit")],
    parent: Annotated[
        str | None,
        Query(
            description="Restrict to children of this geography (e.g. a district"
            " P-code) — used to drill from a district to its local units"
        ),
    ] = None,
) -> GeoDataResponse:
    """Latest value of one indicator for EVERY geography at a level — the
    single call a choropleth map needs. `parent` narrows to one geography's
    children (district → its local units)."""
    if level not in ("province", "district", "local_unit"):
        raise HTTPException(
            status_code=422, detail="level must be 'province', 'district', or 'local_unit'"
        )
    indicator_row = repo.get_indicator(indicator)
    if indicator_row is None:
        raise HTTPException(status_code=404, detail=f"Unknown indicator code: {indicator}")
    result = repo.get_geo_values(indicator, level, parent)
    if result is None:
        where = f" under {parent}" if parent else ""
        raise HTTPException(
            status_code=404,
            detail=f"No {level}-level data for indicator '{indicator}'{where}",
        )
    return GeoDataResponse(
        indicator=IndicatorSummary(
            code=indicator_row.code,
            name=indicator_row.name_en,
            topic=indicator_row.topic,
            unit=indicator_row.unit_code,
            source=indicator_row.source,
            preferred_source=indicator_row.preferred_source,
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


@app.get("/v1/data/geo/breakdown", response_model=GeoBreakdownResponse)
def get_geo_breakdown(
    repo: Annotated[Repository, Depends(get_repository)],
    indicator: Annotated[str, Query(description="Indicator code, e.g. ELECTION_VOTES_PR")],
    level: Annotated[str, Query(description="Geography level: province, district, or local_unit")],
    breakdown_key: Annotated[str, Query(description="Breakdown dimension, e.g. 'party'")],
    period: Annotated[
        str | None,
        Query(
            description="Period label, e.g. '2026'. Omit for the most recent period"
            " present — but pass it whenever a source holds several, or the map"
            " will draw one period under another's label."
        ),
    ] = None,
    breakdown_value: Annotated[
        str | None,
        Query(
            description="Draw only this value of the breakdown (e.g. one party)."
            " Omit for every value, which is what a stacked or share map needs."
        ),
    ] = None,
) -> GeoBreakdownResponse:
    """A broken-down choropleth in ONE request.

    `/v1/data/geo` serves only headline rows (`breakdowns = {}`). Election data
    has no headline row — every observation carries a party — so a party map
    needs this instead. Each geography's total across the breakdown is included
    so a share can be drawn client-side.
    """
    if level not in ("province", "district", "local_unit"):
        raise HTTPException(
            status_code=422, detail="level must be 'province', 'district', or 'local_unit'"
        )
    indicator_row = repo.get_indicator(indicator)
    if indicator_row is None:
        raise HTTPException(status_code=404, detail=f"Unknown indicator code: {indicator}")
    result = repo.get_geo_breakdown(indicator, level, breakdown_key, period, breakdown_value)
    if result is None:
        when = f" for period '{period}'" if period else ""
        raise HTTPException(
            status_code=404,
            detail=f"No {level}-level data broken down by '{breakdown_key}'"
            f" for indicator '{indicator}'{when}",
        )
    return GeoBreakdownResponse(
        indicator=IndicatorSummary(
            code=indicator_row.code,
            name=indicator_row.name_en,
            topic=indicator_row.topic,
            unit=indicator_row.unit_code,
            source=indicator_row.source,
            preferred_source=indicator_row.preferred_source,
        ),
        level=result.level,
        period=result.period,
        breakdown_key=result.breakdown_key,
        unit_code=result.unit_code,
        unit_name=result.unit_name,
        provenance=Provenance(
            source=result.source_name,
            dataset=result.dataset_name,
            license=result.license,
            latest_release_date=result.latest_release_date,
        ),
        geographies=[
            GeoValue(geo_code=g.geo_code, name=g.name_en, name_ne=g.name_ne, value=float(g.value))
            for g in result.geographies
        ],
        cells=[
            GeoBreakdownCell(geo=c.geo_code, key=c.breakdown_value, value=float(c.value))
            for c in result.cells
        ],
    )


@app.get("/v1/data/seasonality", response_model=SeasonalityResponse)
def get_seasonality(
    repo: Annotated[Repository, Depends(get_repository)],
    indicator: Annotated[str, Query(description="Indicator code, e.g. KALIMATI_PRICE_AVG")],
    geo: Annotated[str, Query(description="Geography code")] = "NP",
    breakdown_key: Annotated[
        str, Query(description="Breakdown dimension to group by, e.g. 'commodity'")
    ] = "commodity",
) -> SeasonalityResponse:
    """Average by calendar month, per breakdown value — the shape a seasonality
    chart or a month-by-commodity grid consumes in ONE request.

    Without it the browser would fetch every commodity's full daily series —
    around 100,000 observations — to draw a 25x12 grid.
    """
    indicator_row = repo.get_indicator(indicator)
    if indicator_row is None:
        raise HTTPException(status_code=404, detail=f"Unknown indicator code: {indicator}")
    points = repo.get_seasonality(indicator, geo, breakdown_key)
    # Provenance comes from the series itself, so a seasonal average is never
    # shown without the source that produced it. If the series is missing then
    # so are the averages, so one check covers both.
    series = repo.get_series(indicator, geo, metadata_only=True)
    if not points or series is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No data for indicator '{indicator}' in geography '{geo}' "
                f"broken down by '{breakdown_key}'"
            ),
        )
    return SeasonalityResponse(
        indicator=IndicatorSummary(
            code=indicator_row.code,
            name=indicator_row.name_en,
            topic=indicator_row.topic,
            unit=indicator_row.unit_code,
            source=indicator_row.source,
            preferred_source=indicator_row.preferred_source,
        ),
        geography_code=geo,
        unit_code=series.unit_code,
        unit_name=series.unit_name,
        breakdown_key=breakdown_key,
        provenance=Provenance(
            source=series.source_name,
            dataset=series.dataset_name,
            license=series.license,
            latest_release_date=series.latest_release_date,
        ),
        points=[
            SeasonalityPoint(
                breakdown_value=p.breakdown_value,
                month=p.month,
                mean_value=float(p.mean_value),
                days=p.days,
            )
            for p in bounded(points, MAX_SEASONALITY_ROWS)
        ],
    )


@app.get("/v1/data", response_model=DataResponse)
def get_data(
    repo: Annotated[Repository, Depends(get_repository)],
    indicator: Annotated[str, Query(description="Indicator code, e.g. GDP_GROWTH")],
    geo: Annotated[str, Query(description="Geography code, e.g. NP")] = "NP",
    breakdown_key: Annotated[
        str | None,
        Query(description="Breakdown dimension to filter on, e.g. 'commodity'"),
    ] = None,
    breakdown_value: Annotated[
        str | None,
        Query(description="Value of that dimension, e.g. 'Tomato Small(Local)'"),
    ] = None,
    start: Annotated[
        date | None, Query(description="Earliest period to return (YYYY-MM-DD), with `end`")
    ] = None,
    end: Annotated[
        date | None, Query(description="Latest period to return (YYYY-MM-DD), with `start`")
    ] = None,
) -> DataResponse:
    # Both or neither: a key without a value would silently return the whole
    # series, which for the daily price data is 106,236 observations where the
    # caller asked for one commodity.
    if (breakdown_key is None) != (breakdown_value is None):
        raise HTTPException(
            status_code=422,
            detail="breakdown_key and breakdown_value must be given together",
        )
    validate_window(breakdown_key, breakdown_value, start, end)
    indicator_row = repo.get_indicator(indicator)
    if indicator_row is None:
        raise HTTPException(status_code=404, detail=f"Unknown indicator code: {indicator}")
    series = repo.get_series(indicator, geo, breakdown_key, breakdown_value, start, end)
    if series is None:
        where = f" with {breakdown_key}='{breakdown_value}'" if breakdown_key is not None else ""
        raise HTTPException(
            status_code=404,
            detail=f"No data for indicator '{indicator}' in geography '{geo}'{where}",
        )
    return DataResponse(
        indicator=IndicatorSummary(
            code=indicator_row.code,
            name=indicator_row.name_en,
            topic=indicator_row.topic,
            unit=indicator_row.unit_code,
            source=indicator_row.source,
            preferred_source=indicator_row.preferred_source,
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
                period=o.period,
                value=float(o.value),
                status=o.status,
                footnote=o.footnote,
                release_date=o.release_date,
                breakdowns=o.breakdowns,
            )
            for o in bounded(series.observations)
        ],
    )


def _incident_provenance(row: IncidentRow) -> Provenance:
    """Where an incident came from. Identical for every row of one dataset, but
    carried on the row so a single-incident response can state it too."""
    return Provenance(
        source=row.source_name,
        dataset=row.dataset_name,
        license=row.license,
        latest_release_date=row.latest_release_date,
    )


def _incident(row: IncidentRow) -> Incident:
    """One stored incident as the API publishes it.

    The counts pass through untouched, nulls included: a null is the source
    publishing no figure and a zero is the source counting none, and the JSON
    must keep them apart.
    """
    return Incident(
        id=row.id,
        hazard=row.hazard_code,
        hazard_name=row.hazard_name,
        title=row.title_en,
        title_ne=row.title_ne,
        geo_code=row.geo_code,
        geo_name=row.geo_name,
        lat=row.lat,
        lon=row.lon,
        incident_on=row.incident_on,
        deaths=row.deaths,
        missing=row.missing,
        injured=row.injured,
        affected_families=row.affected_families,
        houses_destroyed=row.houses_destroyed,
        estimated_loss_npr=(
            float(row.estimated_loss_npr) if row.estimated_loss_npr is not None else None
        ),
        verified=row.verified,
    )


@app.get("/v1/hazards", response_model=list[HazardSummary])
def list_hazards(
    repo: Annotated[Repository, Depends(get_repository)],
) -> list[HazardSummary]:
    """The hazard types Nepal actually records, commonest first.

    Only hazards with at least one incident are returned: the publisher defines
    47, and a map legend listing volcanic eruptions Nepal has never recorded
    tells a reader nothing.
    """
    return [
        HazardSummary(
            code=h.code,
            name_en=h.name_en,
            name_ne=h.name_ne,
            hazard_type=h.hazard_type,
            color=h.color,
            incidents=h.incidents,
        )
        for h in repo.list_hazards()
    ]


@app.get("/v1/incidents", response_model=IncidentsResponse)
def list_incidents(
    repo: Annotated[Repository, Depends(get_repository)],
    start: Annotated[
        date | None, Query(description="Earliest incident date (YYYY-MM-DD)")
    ] = None,
    end: Annotated[date | None, Query(description="Latest incident date (YYYY-MM-DD)")] = None,
    hazard: Annotated[
        str | None, Query(description="One hazard code, e.g. 'flood' (see /v1/hazards)")
    ] = None,
    geo: Annotated[
        str | None,
        Query(description="P-code; matches this geography and everything beneath it"),
    ] = None,
    bbox: Annotated[
        str | None,
        Query(description="Map window as min_lon,min_lat,max_lon,max_lat"),
    ] = None,
) -> IncidentsResponse:
    """Individual recorded disasters — the data behind the incident map.

    Unlike every other endpoint here, this returns EVENTS rather than
    statistics: things that happened, at a place, on a day. The response is
    capped at MAX_INCIDENT_ROWS and ordered newest first, so a caller with no
    filters gets a real, recent window rather than a truncated arbitrary slice.
    Narrow it with `start`/`end`, `hazard`, `geo` or `bbox`.
    """
    validate_window(None, None, start, end)
    box: tuple[float, float, float, float] | None = None
    if bbox is not None:
        parts = bbox.split(",")
        if len(parts) != 4:
            raise HTTPException(
                status_code=422, detail="bbox must be min_lon,min_lat,max_lon,max_lat"
            )
        try:
            min_lon, min_lat, max_lon, max_lat = (float(p) for p in parts)
        except ValueError:
            raise HTTPException(status_code=422, detail="bbox values must be numbers") from None
        if min_lon > max_lon or min_lat > max_lat:
            raise HTTPException(status_code=422, detail="bbox is inside out")
        box = (min_lon, min_lat, max_lon, max_lat)

    found = repo.list_incidents(
        start=start, end=end, hazard=hazard, geography_code=geo, bbox=box
    )
    if not found.rows:
        raise HTTPException(status_code=404, detail="No incidents match that request")
    first = found.rows[0]
    filters = {
        name: value
        for name, value in (
            ("start", str(start) if start else ""),
            ("end", str(end) if end else ""),
            ("hazard", hazard or ""),
            ("geo", geo or ""),
            ("bbox", bbox or ""),
        )
        if value
    }
    return IncidentsResponse(
        provenance=_incident_provenance(first),
        filters=filters,
        total_matching=found.total_matching,
        total_shown=len(found.rows),
        truncated=found.total_matching > len(found.rows),
        incidents=[_incident(r) for r in found.rows],
    )


@app.get("/v1/incidents/{incident_id}", response_model=IncidentDetail)
def get_incident(
    incident_id: int,
    repo: Annotated[Repository, Depends(get_repository)],
) -> IncidentDetail:
    """One recorded disaster, by its id.

    The listing is a window that moves as filters change, so it is no address
    for a particular event. This is: what a link to a single incident resolves
    to, and what a reader following one from elsewhere lands on.
    """
    row = repo.get_incident(incident_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No incident {incident_id}")
    return IncidentDetail(provenance=_incident_provenance(row), incident=_incident(row))
