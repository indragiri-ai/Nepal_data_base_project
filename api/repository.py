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
    # Populated by list_indicators (for the headline-answer badge, decision 0005):
    # `source` is the indicator's own origin; `preferred_source` is the headline
    # source for its concept. When they differ, this is an alternative estimate.
    source: str | None = None
    preferred_source: str | None = None


@dataclass(frozen=True)
class IndicatorSparkRow:
    """One indicator's compact national trend, for the sector-page cards: the
    latest value and a short run of recent values (chronological, most-recent
    last) to draw a sparkline. One row per indicator, built in a single query."""

    code: str
    latest_period: str
    latest_value: Decimal
    points: list[Decimal]


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


@dataclass(frozen=True)
class GeoValueRow:
    geo_code: str
    name_en: str
    name_ne: str | None
    value: Decimal


@dataclass(frozen=True)
class GeoValuesResult:
    indicator_code: str
    indicator_name: str
    level: str
    period: str
    unit_code: str
    unit_name: str
    source_name: str
    dataset_name: str
    license: str | None
    latest_release_date: str
    values: list[GeoValueRow]


@dataclass(frozen=True)
class DatasetMetaRow:
    dataset: str
    source: str
    last_updated: str | None  # date of the latest successful ingestion, or None
    latest_release_date: str | None


class Repository(Protocol):
    def list_indicators(self) -> list[IndicatorRow]: ...
    def get_spark_series(self) -> list[IndicatorSparkRow]: ...
    def get_indicator(self, code: str) -> IndicatorRow | None: ...
    def get_series(self, indicator_code: str, geography_code: str) -> SeriesResult | None: ...
    def get_geo_values(self, indicator_code: str, level: str) -> GeoValuesResult | None: ...
    def get_meta(self) -> list[DatasetMetaRow]: ...


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
        """Every indicator that actually has at least one observation.

        An indicator with no data cannot be charted, so listing it advertises
        something the portal cannot deliver — the browser renders an empty chart.
        Reference rows legitimately exist before their data lands (seeding and
        ingestion are separate steps, and ingestion of a large catalogue takes
        many minutes), so the listing filters rather than assuming they arrive
        together.
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT i.code, i.name_en, i.name_ne, i.definition_en, i.topic,"
                " u.code, u.name_en, i.source_concept,"
                " os.name_en AS origin_source, ps.name_en AS preferred_source"
                " FROM indicators i"
                " JOIN units u ON u.id = i.unit_id"
                " LEFT JOIN sources os ON os.id = i.origin_source_id"
                " LEFT JOIN sources ps ON ps.id = i.preferred_source_id"
                " WHERE EXISTS (SELECT 1 FROM observations o WHERE o.indicator_id = i.id)"
                " ORDER BY i.topic, i.code"
            )
            return [
                IndicatorRow(
                    code=r[0], name_en=r[1], name_ne=r[2], definition_en=r[3],
                    topic=r[4], unit_code=r[5], unit_name=r[6], source_concept=r[7],
                    source=r[8], preferred_source=r[9],
                )
                for r in cur.fetchall()
            ]

    def get_indicator(self, code: str) -> IndicatorRow | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {_INDICATOR_COLUMNS} WHERE i.code = %s", (code,))
            row = cur.fetchone()
        return IndicatorRow(*row) if row is not None else None

    def get_spark_series(self, max_points: int = 16) -> list[IndicatorSparkRow]:
        """Every indicator's national trend in ONE query, for the sector cards.

        Picks a single headline series per indicator+period: the empty-breakdown
        row (country-level WB, census all-sexes) if present, else the aggregate
        NRB bank class (overall, then commercial_banks) — the same headline slice
        the charts use, done server-side so the page makes one request, not one
        per indicator.
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "WITH picked AS ("
                "  SELECT o.indicator_id, t.gregorian_label AS period, t.sort_key,"
                "    o.value,"
                "    row_number() OVER ("
                "      PARTITION BY o.indicator_id, o.time_period_id"
                "      ORDER BY CASE"
                "        WHEN o.breakdowns = '{}'::jsonb THEN 0"
                "        WHEN o.breakdowns->>'bfi_class' = 'overall' THEN 1"
                "        WHEN o.breakdowns->>'bfi_class' = 'commercial_banks' THEN 2"
                "        ELSE 3 END, o.id"
                "    ) AS rn"
                "  FROM observations o"
                "  JOIN geographies g ON g.id = o.geography_id"
                "  JOIN time_periods t ON t.id = o.time_period_id"
                "  WHERE g.code = 'NP' AND o.is_latest"
                ")"
                " SELECT i.code, p.period, p.value"
                " FROM picked p JOIN indicators i ON i.id = p.indicator_id"
                " WHERE p.rn = 1"
                " ORDER BY i.code, p.sort_key",
            )
            rows = cur.fetchall()
        by_code: dict[str, list[tuple[str, Decimal]]] = {}
        for code, period, value in rows:
            by_code.setdefault(code, []).append((period, value))
        result: list[IndicatorSparkRow] = []
        for code, pts in by_code.items():
            recent = pts[-max_points:]
            result.append(
                IndicatorSparkRow(
                    code=code,
                    latest_period=recent[-1][0],
                    latest_value=recent[-1][1],
                    points=[v for _, v in recent],
                )
            )
        return result

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

    def get_geo_values(self, indicator_code: str, level: str) -> GeoValuesResult | None:
        """Latest headline value (breakdowns = {}) of one indicator for EVERY
        geography at a level — the shape a choropleth map needs in one call."""
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT g.code, g.name_en, g.name_ne, o.value,"
                " t.gregorian_label, i.name_en, u.code, u.name_en,"
                " s.name_en, d.name_en, d.license, r.release_date"
                " FROM observations o"
                " JOIN indicators i ON i.id = o.indicator_id"
                " JOIN geographies g ON g.id = o.geography_id"
                " JOIN time_periods t ON t.id = o.time_period_id"
                " JOIN units u ON u.id = o.unit_id"
                " JOIN datasets d ON d.id = o.dataset_id"
                " JOIN sources s ON s.id = d.source_id"
                " JOIN releases r ON r.id = o.release_id"
                " WHERE i.code = %s AND g.level = %s AND o.is_latest"
                "   AND o.breakdowns = '{}'::jsonb"
                " ORDER BY g.code",
                (indicator_code, level),
            )
            rows = cur.fetchall()
        if not rows:
            return None
        first = rows[0]
        return GeoValuesResult(
            indicator_code=indicator_code,
            indicator_name=first[5],
            level=level,
            period=first[4],
            unit_code=first[6],
            unit_name=first[7],
            source_name=first[8],
            dataset_name=first[9],
            license=first[10],
            latest_release_date=max(str(row[11]) for row in rows),
            values=[
                GeoValueRow(geo_code=r[0], name_en=r[1], name_ne=r[2], value=r[3])
                for r in rows
            ],
        )

    def get_meta(self) -> list[DatasetMetaRow]:
        """Per-dataset freshness: the date of the latest SUCCESSFUL ingestion
        run and the most recent release date. Only datasets that have loaded
        at least once appear. Powers the site's 'Data updated' line."""
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT d.name_en, s.name_en,"
                " MAX(il.finished_at) FILTER (WHERE il.status = 'success') AS last_success,"
                " MAX(r.release_date) FILTER (WHERE il.status = 'success') AS latest_release"
                " FROM datasets d"
                " JOIN sources s ON s.id = d.source_id"
                " JOIN ingestion_log il ON il.dataset_id = d.id"
                " LEFT JOIN releases r ON r.id = il.release_id"
                " GROUP BY d.id, d.name_en, s.name_en"
                " HAVING MAX(il.finished_at) FILTER (WHERE il.status = 'success') IS NOT NULL"
                " ORDER BY last_success DESC"
            )
            rows = cur.fetchall()
        return [
            DatasetMetaRow(
                dataset=row[0],
                source=row[1],
                last_updated=row[2].date().isoformat() if row[2] is not None else None,
                latest_release_date=str(row[3]) if row[3] is not None else None,
            )
            for row in rows
        ]
