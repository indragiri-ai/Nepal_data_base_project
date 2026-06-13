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


class DataResponse(BaseModel):
    indicator: IndicatorSummary
    geography_code: str
    geography_name: str
    unit_code: str
    unit_name: str
    provenance: Provenance
    observations: list[Observation]
