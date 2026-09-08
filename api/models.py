"""Pydantic response models for the API (P1.S10).

These define the shape of every JSON response and power the auto-generated docs
at /docs. Every data response carries a provenance block (Master Prompt §3.5).
"""

from __future__ import annotations

from pydantic import BaseModel


class IndicatorSummary(BaseModel):
    code: str
    name: str
    topic: str
    unit: str
    # Headline-answer policy (decision 0005), populated by /v1/indicators.
    # `source` is where this indicator's data comes from; `preferred_source` is
    # the headline source for its concept. When they differ, this series is an
    # alternative estimate and the UI badges it "alternative estimate — {source}".
    source: str | None = None
    preferred_source: str | None = None


class IndicatorSpark(BaseModel):
    """One indicator's compact national trend for the sector cards: the latest
    value and a short run of recent values (chronological) for a sparkline."""

    code: str
    latest_period: str
    latest_value: float
    points: list[float]


class IndicatorDetail(BaseModel):
    code: str
    name_en: str
    name_ne: str | None
    definition_en: str | None
    topic: str
    unit_code: str
    unit_name: str
    source_concept: str | None


class Provenance(BaseModel):
    source: str
    dataset: str
    license: str | None
    latest_release_date: str


class Observation(BaseModel):
    period: str
    value: float
    status: str
    footnote: str | None
    release_date: str
    # e.g. {"bfi_class": "commercial_banks"} for NRB banking series; empty for
    # country-level series (World Bank). Clients group/filter by these keys.
    breakdowns: dict[str, str] = {}


class DataResponse(BaseModel):
    indicator: IndicatorSummary
    geography_code: str
    geography_name: str
    unit_code: str
    unit_name: str
    provenance: Provenance
    observations: list[Observation]


class GeoValue(BaseModel):
    geo_code: str
    name: str
    name_ne: str | None
    value: float


class SeasonalityPoint(BaseModel):
    """One breakdown value's average for one month of the YEAR (1-12)."""

    breakdown_value: str
    month: int
    mean_value: float
    days: int


class SeasonalityResponse(BaseModel):
    """Every January collapsed into one number, per breakdown value.

    Answers "when is this cheapest?" — a question a time series cannot show
    and that the market board's own site does not attempt. `days` travels with
    each average so a reader can weigh what it rests on.
    """

    indicator: IndicatorSummary
    geography_code: str
    unit_code: str
    unit_name: str
    breakdown_key: str
    provenance: Provenance
    points: list[SeasonalityPoint]


class GeoDataResponse(BaseModel):
    """One indicator's latest value for every geography at a level — the shape
    a choropleth map consumes in a single request."""

    indicator: IndicatorSummary
    level: str
    period: str
    unit_code: str
    unit_name: str
    provenance: Provenance
    values: list[GeoValue]


class GeoBreakdownCell(BaseModel):
    """One geography's value for one breakdown value — one party's votes in one
    district. `geo` is the P-code; `key` is the breakdown value."""

    geo: str
    key: str
    value: float


class GeoBreakdownResponse(BaseModel):
    """A broken-down choropleth in one request: every breakdown value for every
    geography at a level, for ONE period, plus each geography's total.

    The plain `/v1/data/geo` cannot serve this — it returns only headline rows
    (no breakdowns), and data like election results has no headline row at all.
    The totals are supplied so a share can be drawn without the caller summing
    thousands of cells, and without a derived total being stored as if the
    source had published it.
    """

    indicator: IndicatorSummary
    level: str
    period: str
    breakdown_key: str
    unit_code: str
    unit_name: str
    provenance: Provenance
    geographies: list[GeoValue]  # `value` is that geography's total
    cells: list[GeoBreakdownCell]


class DatasetMeta(BaseModel):
    """Freshness of one dataset: when its pipeline last succeeded and the date
    of its most recent data release."""

    dataset: str
    source: str
    # Date (YYYY-MM-DD) of the latest SUCCESSFUL ingestion run, or null if the
    # dataset has never loaded successfully.
    last_updated: str | None
    # Date of the most recent data release for the dataset, or null.
    latest_release_date: str | None


class MetaResponse(BaseModel):
    """Portal-wide freshness. `data_updated` is the most recent successful
    ingestion across all datasets — the single date the site footer shows."""

    data_updated: str | None
    datasets: list[DatasetMeta]


class SearchHit(BaseModel):
    """One global-search match (SRCH.S1).

    `kind` is 'indicator' (a dataset the portal can chart) or 'geography' (a
    place), so the UI can group results. `detail` is the kind's qualifier — an
    indicator's topic, or a geography's level. `unit` is null for geographies.
    """

    kind: str
    code: str
    name: str
    name_ne: str | None
    detail: str
    unit: str | None


class SearchResponse(BaseModel):
    """Results for one search. `total` is the number of hits returned, which is
    capped by `limit` — no match is a valid answer, returned as an empty list
    rather than a 404."""

    query: str
    total: int
    results: list[SearchHit]


class HazardSummary(BaseModel):
    """One hazard type, as the publisher defines it — used for map legends and
    filter controls. `color` is BIPAD's own colour for the hazard, so the
    portal's legend matches the government's."""

    code: str
    name_en: str
    name_ne: str | None
    hazard_type: str  # 'natural' | 'non_natural'
    color: str | None
    incidents: int


class Incident(BaseModel):
    """ONE recorded disaster: a thing that happened, at a place, on a day.

    Every other response in this API describes a statistic — a number about a
    period and a place. This describes an event, which is why it carries a
    point rather than only a geography, and why the counts may be null: a null
    means the source published no figure, where 0 means it published a zero.

    `lat`/`lon` can be absent even though the event is placed: the historical
    archive records the district but never a coordinate.
    """

    id: int
    hazard: str
    hazard_name: str
    title: str
    title_ne: str | None
    geo_code: str
    geo_name: str
    lat: float | None
    lon: float | None
    incident_on: str
    deaths: int | None
    missing: int | None
    injured: int | None
    affected_families: int | None
    houses_destroyed: int | None
    estimated_loss_npr: float | None
    verified: bool


class IncidentsResponse(BaseModel):
    """A bounded window on the incident record, with its provenance.

    THREE numbers, and they mean different things. `total_matching` is how many
    incidents the filters found; `total_shown` is how many this response
    carries; `truncated` says plainly whether the second is smaller than the
    first. A client reading only `total_shown` and calling it a total would be
    describing the server's row cap as a fact about Nepal — exactly the
    misreading these three fields exist to prevent.

    When `truncated` is true the rows are the MOST RECENT matches, not a sample.
    Say so wherever they are drawn: the newest 2,000 of a year are that year's
    late months and nothing else.
    """

    provenance: Provenance
    filters: dict[str, str]
    total_matching: int
    total_shown: int
    truncated: bool
    incidents: list[Incident]


class IncidentDetail(BaseModel):
    """One incident, addressed by its own id — what a permalink resolves to."""

    provenance: Provenance
    incident: Incident
