"""Census 2021 layout: indicator registry + pure parsers for the NSO census API.

The National Statistics Office publishes Census 2021 results through the API
behind censusresults.nsonepal.gov.np (base: censusapi.cbs.gov.np/api/v1 — see
reference/census/PROVENANCE.md for how it was discovered and verified). Two
endpoints feed the portal's population dashboard:

  /population/highlight  -> total/male/female population, sex ratio, density,
                            annual growth rate
  /literacy              -> literacy rate (read & write, population 5+), by sex

Both accept ?province=&district= filters; the same shapes come back at every
level, so ONE parser serves national, province, and district payloads.

This module is PURE (no I/O): the registry is the single source of truth for
db/seeds/indicators_census.csv (a test locks them in sync), and the parsers
raise CensusParseError on any unexpected shape — report, never guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

CENSUS_YEAR = 2021


class CensusParseError(Exception):
    """An NSO payload did not look like we verified it should — fail loudly."""


@dataclass(frozen=True)
class CensusIndicator:
    code: str
    name_en: str
    definition_en: str
    unit_code: str
    topic: str
    source_concept: str  # endpoint + field path inside the NSO response


REGISTRY: tuple[CensusIndicator, ...] = (
    CensusIndicator(
        code="CENSUS_POP_TOTAL",
        name_en="Population (Census 2021)",
        definition_en=(
            "Total enumerated population, National Population and Housing Census"
            " 2021. Breakdowns: sex (male/female)."
        ),
        unit_code="PERSONS",
        topic="population",
        source_concept="population/highlight:total|male|female",
    ),
    CensusIndicator(
        code="CENSUS_SEX_RATIO",
        name_en="Sex ratio (Census 2021)",
        definition_en="Males per 100 females, Census 2021.",
        unit_code="RATIO",
        topic="population",
        source_concept="population/highlight:sex_ratio",
    ),
    CensusIndicator(
        code="CENSUS_POP_DENSITY",
        name_en="Population density (Census 2021)",
        definition_en="Persons per square kilometre, Census 2021.",
        unit_code="PER_KM2",
        topic="population",
        source_concept="population/highlight:density",
    ),
    CensusIndicator(
        code="CENSUS_POP_GROWTH",
        name_en="Annual population growth rate (Census 2021)",
        definition_en=(
            "Average annual population growth rate over 2011-2021 (exponential),"
            " as published with Census 2021."
        ),
        unit_code="PCT",
        topic="population",
        source_concept="population/highlight:growth_rate",
    ),
    CensusIndicator(
        code="CENSUS_LITERACY_RATE",
        name_en="Literacy rate (Census 2021)",
        definition_en=(
            "Share of population aged 5+ who can both read and write, Census"
            " 2021. Breakdowns: sex (male/female)."
        ),
        unit_code="PCT",
        topic="education",
        source_concept="literacy:literacyBySex.read_write",
    ),
)


@dataclass(frozen=True)
class ParsedValue:
    """One value parsed out of an NSO payload, ready to become an observation."""

    indicator_code: str
    value: Decimal
    breakdowns: dict[str, str]


def _require(data: dict[str, Any], key: str, context: str) -> Any:
    if key not in data or data[key] is None:
        raise CensusParseError(f"{context}: missing field '{key}'")
    return data[key]


def _decimal(raw: Any, context: str) -> Decimal:
    try:
        d = Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise CensusParseError(f"{context}: non-numeric value {raw!r}") from exc
    if not d.is_finite():
        raise CensusParseError(f"{context}: non-finite value {raw!r}")
    return d


def unwrap(payload: dict[str, Any], context: str) -> dict[str, Any]:
    """Every NSO response is {status, code, success, data} — return data."""
    if not payload.get("success") or "data" not in payload:
        raise CensusParseError(f"{context}: response did not report success")
    data = payload["data"]
    if not isinstance(data, dict):
        raise CensusParseError(f"{context}: 'data' is not an object")
    return data


def parse_highlight(payload: dict[str, Any], context: str) -> list[ParsedValue]:
    """Parse /population/highlight into population, sex ratio, density, growth."""
    data = unwrap(payload, context)
    out = [
        ParsedValue("CENSUS_POP_TOTAL", _decimal(_require(data, "total", context), context), {}),
        ParsedValue(
            "CENSUS_POP_TOTAL",
            _decimal(_require(data, "male", context), context),
            {"sex": "male"},
        ),
        ParsedValue(
            "CENSUS_POP_TOTAL",
            _decimal(_require(data, "female", context), context),
            {"sex": "female"},
        ),
        ParsedValue(
            "CENSUS_SEX_RATIO", _decimal(_require(data, "sex_ratio", context), context), {}
        ),
        ParsedValue(
            "CENSUS_POP_DENSITY", _decimal(_require(data, "density", context), context), {}
        ),
        ParsedValue(
            "CENSUS_POP_GROWTH", _decimal(_require(data, "growth_rate", context), context), {}
        ),
    ]
    return out


def parse_literacy(payload: dict[str, Any], context: str) -> list[ParsedValue]:
    """Parse /literacy -> literacyBySex 'read_write' shares for Total/Male/Female."""
    data = unwrap(payload, context)
    block = _require(data, "literacyBySex", context)
    categories = _require(block, "categories", context)
    if "read_write" not in categories:
        raise CensusParseError(f"{context}: 'read_write' not in literacy categories")
    idx = categories.index("read_write")

    breakdown_by_name = {"Total": {}, "Male": {"sex": "male"}, "Female": {"sex": "female"}}
    out: list[ParsedValue] = []
    seen: set[str] = set()
    for series in _require(block, "series", context):
        name = series.get("name")
        if name not in breakdown_by_name:
            raise CensusParseError(f"{context}: unexpected literacy series {name!r}")
        values = series.get("data") or []
        if len(values) <= idx:
            raise CensusParseError(f"{context}: literacy series {name!r} too short")
        out.append(
            ParsedValue(
                "CENSUS_LITERACY_RATE",
                _decimal(values[idx], f"{context}:{name}"),
                dict(breakdown_by_name[name]),
            )
        )
        seen.add(name)
    if seen != set(breakdown_by_name):
        raise CensusParseError(f"{context}: literacy series incomplete, saw {sorted(seen)}")
    return out
