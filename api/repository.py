"""Data access for the API (P1.S10).

A thin repository layer that reads the warehouse. Splitting it behind a Protocol
lets the API routes depend on an interface, so tests can inject a fake repository
and run offline (no database) while production uses PostgresRepository.

Read-only: there are no write methods anywhere.
"""

from __future__ import annotations

from collections.abc import Sequence
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


@dataclass(frozen=True)
class SearchHitRow:
    """One global-search match (SRCH.S1), from either dimension table.

    `kind` says which table it came from, so the UI can group results:
    'indicator' (a dataset the portal can chart) or 'geography' (a place).
    `detail` carries the kind's natural qualifier — an indicator's topic or a
    geography's level — so one row shape serves both. `unit_code` is None for
    geographies. `score` is the relevance rank; higher sorts first.
    """

    kind: str
    code: str
    name_en: str
    name_ne: str | None
    detail: str
    unit_code: str | None
    score: int


class Repository(Protocol):
    def list_indicators(self) -> list[IndicatorRow]: ...
    def get_spark_series(self) -> list[IndicatorSparkRow]: ...
    def get_indicator(self, code: str) -> IndicatorRow | None: ...
    def get_series(
        self,
        indicator_code: str,
        geography_code: str,
        breakdown_key: str | None = None,
        breakdown_value: str | None = None,
    ) -> SeriesResult | None: ...
    def get_geo_values(
        self, indicator_code: str, level: str, parent_code: str | None = None
    ) -> GeoValuesResult | None: ...
    def get_meta(self) -> list[DatasetMetaRow]: ...
    def search(self, term: str, limit: int = 20) -> list[SearchHitRow]: ...


def escape_like(term: str) -> str:
    """Neutralise LIKE wildcards in user input (SRCH.S1).

    `%` and `_` are wildcards inside ILIKE, so an unescaped `%` typed into the
    search box would match every row in the catalogue. The backslash must be
    escaped first, or it would double-escape the escapes added after it. Paired
    with `ESCAPE '\\'` in every ILIKE below.
    """
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# Column positions in the get_geo_values row tuple that this helper cares about.
_GEO_SORT_KEY = 12


def latest_period_rows(rows: Sequence[Any]) -> list[Any]:
    """Keep only the rows belonging to the newest period in the result set.

    A choropleth shows ONE year. The query behind it returns every year a
    geography has (see `get_geo_values`), so without this the map would draw a
    value from an arbitrary year under the label of another — the kind of
    quietly wrong number this portal exists not to publish.

    "Newest" is decided by `time_periods.sort_key`, the column whose whole job
    is ordering periods along the timeline; comparing the display labels would
    sort 'FY 2019/20' after 'FY 2023/24' in some fiscal-year spellings.

    Geographies with no data in that newest period are simply absent — the map
    leaves them blank rather than back-filling an older year, which would put
    two different years in one picture.
    """
    if not rows:
        return []
    newest = max(r[_GEO_SORT_KEY] for r in rows)
    return [r for r in rows if r[_GEO_SORT_KEY] == newest]


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

    def get_series(
        self,
        indicator_code: str,
        geography_code: str,
        breakdown_key: str | None = None,
        breakdown_value: str | None = None,
    ) -> SeriesResult | None:
        """One indicator's series for one geography, optionally ONE breakdown.

        The breakdown filter exists because some series are enormous when taken
        whole: the Kalimati daily prices are 76,747 observations per indicator
        across 25 commodities, so a chart of one vegetable would otherwise mean
        sending every vegetable to the browser and throwing 24/25 of it away.
        """
        breakdown_filter = ""
        params: list[str] = [indicator_code, geography_code]
        if breakdown_key is not None and breakdown_value is not None:
            breakdown_filter = " AND o.breakdowns->>%s = %s"
            params += [breakdown_key, breakdown_value]
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
                + breakdown_filter
                + " ORDER BY t.sort_key",
                tuple(params),
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

    def get_geo_values(
        self, indicator_code: str, level: str, parent_code: str | None = None
    ) -> GeoValuesResult | None:
        """Latest headline value (breakdowns = {}) of one indicator for EVERY
        geography at a level — the shape a choropleth map needs in one call.

        `parent_code` narrows the set to children of one geography — used to drill
        from a district to its local units (P2B.S8), so the map/table shows just
        that district's municipalities rather than all 753 nationally.

        ONE period, not all of them. `is_latest` marks the newest *release* of a
        cell, not the newest year — every year of a series carries it. So this
        query returns one row per geography per year, and the caller must pick
        the year or a map draws whichever row happens to win, under a label
        borrowed from a different year. Census data hid this for months (a
        census has one year); the provincial fiscal series, six years deep, is
        the first data at this level where it bites. `latest_period_rows` does
        the picking.
        """
        parent_filter = ""
        params: list[str] = [indicator_code, level]
        if parent_code is not None:
            parent_filter = " AND g.parent_id = (SELECT id FROM geographies WHERE code = %s)"
            params.append(parent_code)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT g.code, g.name_en, g.name_ne, o.value,"
                " t.gregorian_label, i.name_en, u.code, u.name_en,"
                " s.name_en, d.name_en, d.license, r.release_date, t.sort_key"
                " FROM observations o"
                " JOIN indicators i ON i.id = o.indicator_id"
                " JOIN geographies g ON g.id = o.geography_id"
                " JOIN time_periods t ON t.id = o.time_period_id"
                " JOIN units u ON u.id = o.unit_id"
                " JOIN datasets d ON d.id = o.dataset_id"
                " JOIN sources s ON s.id = d.source_id"
                " JOIN releases r ON r.id = o.release_id"
                " WHERE i.code = %s AND g.level = %s AND o.is_latest"
                "   AND o.breakdowns = '{}'::jsonb" + parent_filter +
                " ORDER BY g.code",
                tuple(params),
            )
            all_rows = cur.fetchall()
        rows = latest_period_rows(all_rows)
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

    def search(self, term: str, limit: int = 20) -> list[SearchHitRow]:
        """Find indicators and geographies whose text matches `term` (SRCH.S1).

        Matching is case-insensitive substring (ILIKE), NOT Postgres full-text.
        That is deliberate: `to_tsvector` stems against a language config, and
        no Nepali config ships with Postgres — an 'english' vector mangles
        Devanagari, so `name_ne` would be unsearchable. Character-level
        matching is script-agnostic and works for both name columns.

        No index backs this. The two dimension tables together hold on the
        order of 2,700 short rows, where a sequential scan is sub-millisecond;
        a pg_trgm index would cost storage (scarce on the 500 MB tier) to
        solve a problem this size does not have.

        Indicators are filtered to those that actually have observations, for
        the same reason `list_indicators` is: a searchable indicator with no
        data is a promise the portal cannot keep.
        """
        contains = f"%{escape_like(term)}%"
        prefix = f"{escape_like(term)}%"
        params = {"term": term, "contains": contains, "prefix": prefix, "limit": limit}
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT kind, code, name_en, name_ne, detail, unit_code, score FROM ("
                "  SELECT 'indicator' AS kind, i.code, i.name_en, i.name_ne,"
                "    i.topic AS detail, u.code AS unit_code,"
                "    CASE"
                "      WHEN lower(i.code) = lower(%(term)s) THEN 100"
                "      WHEN i.code ILIKE %(contains)s ESCAPE '\\' THEN 80"
                "      WHEN i.name_en ILIKE %(prefix)s ESCAPE '\\'"
                "        OR i.name_ne ILIKE %(prefix)s ESCAPE '\\' THEN 60"
                "      WHEN i.name_en ILIKE %(contains)s ESCAPE '\\'"
                "        OR i.name_ne ILIKE %(contains)s ESCAPE '\\' THEN 40"
                "      ELSE 20"
                "    END AS score"
                "  FROM indicators i"
                "  JOIN units u ON u.id = i.unit_id"
                "  WHERE EXISTS (SELECT 1 FROM observations o WHERE o.indicator_id = i.id)"
                "    AND (i.code ILIKE %(contains)s ESCAPE '\\'"
                "      OR i.name_en ILIKE %(contains)s ESCAPE '\\'"
                "      OR i.name_ne ILIKE %(contains)s ESCAPE '\\'"
                "      OR i.definition_en ILIKE %(contains)s ESCAPE '\\')"
                "  UNION ALL"
                "  SELECT 'geography' AS kind, g.code, g.name_en, g.name_ne,"
                "    g.level AS detail, NULL AS unit_code,"
                "    CASE"
                "      WHEN lower(g.code) = lower(%(term)s) THEN 100"
                "      WHEN g.code ILIKE %(contains)s ESCAPE '\\' THEN 80"
                "      WHEN g.name_en ILIKE %(prefix)s ESCAPE '\\'"
                "        OR g.name_ne ILIKE %(prefix)s ESCAPE '\\' THEN 60"
                "      ELSE 40"
                "    END AS score"
                "  FROM geographies g"
                "  WHERE g.code ILIKE %(contains)s ESCAPE '\\'"
                "    OR g.name_en ILIKE %(contains)s ESCAPE '\\'"
                "    OR g.name_ne ILIKE %(contains)s ESCAPE '\\'"
                ") hits"
                " ORDER BY score DESC, name_en"
                " LIMIT %(limit)s",
                params,
            )
            rows = cur.fetchall()
        return [
            SearchHitRow(
                kind=r[0], code=r[1], name_en=r[2], name_ne=r[3],
                detail=r[4], unit_code=r[5], score=r[6],
            )
            for r in rows
        ]

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
