"""Data access for the API (P1.S10).

A thin repository layer that reads the warehouse. Splitting it behind a Protocol
lets the API routes depend on an interface, so tests can inject a fake repository
and run offline (no database) while production uses PostgresRepository.

Read-only: there are no write methods anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

import psycopg


@dataclass(frozen=True)
class IndicatorRow:
    code: str
    name_en: str
    name_ne: str | None
    definition_en: str | None
    topic: str
    unit_code: str
    unit_name: str
    source_concept: str | None


@dataclass(frozen=True)
class ObservationRow:
    period: str
    sort_key: int
    value: Decimal
    status: str
    footnote: str | None
    release_date: str
    # e.g. {"bfi_class": "commercial_banks"} for NRB banking series; {} for
    # country-level series such as the World Bank indicators.
    breakdowns: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SeriesResult:
    indicator_code: str
    indicator_name: str
    geography_code: str
    geography_name: str
    unit_code: str
    unit_name: str
    source_name: str
    dataset_name: str
    license: str | None
    latest_release_date: str
    observations: list[ObservationRow]


class Repository(Protocol):
    def list_indicators(self) -> list[IndicatorRow]: ...
    def get_indicator(self, code: str) -> IndicatorRow | None: ...
    def get_series(self, indicator_code: str, geography_code: str) -> SeriesResult | None: ...


_INDICATOR_COLUMNS = (
    "i.code, i.name_en, i.name_ne, i.definition_en, i.topic,"
    " u.code, u.name_en, i.source_concept"
    " FROM indicators i JOIN units u ON u.id = i.unit_id"
)


class PostgresRepository:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def _connect(self) -> psycopg.Connection[Any]:
        return psycopg.connect(self._dsn)

    def list_indicators(self) -> list[IndicatorRow]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {_INDICATOR_COLUMNS} ORDER BY i.topic, i.code")
            return [IndicatorRow(*row) for row in cur.fetchall()]

    def get_indicator(self, code: str) -> IndicatorRow | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {_INDICATOR_COLUMNS} WHERE i.code = %s", (code,))
            row = cur.fetchone()
        return IndicatorRow(*row) if row is not None else None

    def get_series(self, indicator_code: str, geography_code: str) -> SeriesResult | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT t.gregorian_label, t.sort_key, o.value, o.status, o.footnote,"
                " r.release_date, i.name_en, g.name_en, u.code, u.name_en,"
                " s.name_en, d.name_en, d.license, o.breakdowns"
                " FROM observations o"
                " JOIN indicators i ON i.id = o.indicator_id"
                " JOIN geographies g ON g.id = o.geography_id"
                " JOIN time_periods t ON t.id = o.time_period_id"
                " JOIN units u ON u.id = o.unit_id"
                " JOIN datasets d ON d.id = o.dataset_id"
                " JOIN sources s ON s.id = d.source_id"
                " JOIN releases r ON r.id = o.release_id"
                " WHERE i.code = %s AND g.code = %s AND o.is_latest"
                " ORDER BY t.sort_key",
                (indicator_code, geography_code),
            )
            rows = cur.fetchall()
        if not rows:
            return None
        observations = [
            ObservationRow(
                period=row[0], sort_key=row[1], value=row[2], status=row[3],
                footnote=row[4], release_date=str(row[5]), breakdowns=row[13] or {},
            )
            for row in rows
        ]
        first = rows[0]
        return SeriesResult(
            indicator_code=indicator_code,
            indicator_name=first[6],
            geography_code=geography_code,
            geography_name=first[7],
            unit_code=first[8],
            unit_name=first[9],
            source_name=first[10],
            dataset_name=first[11],
            license=first[12],
            latest_release_date=max(str(row[5]) for row in rows),
            observations=observations,
        )
