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
