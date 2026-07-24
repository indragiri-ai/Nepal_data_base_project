"""In-pipeline data-quality gate (P1.S9, Master Prompt §3.3).

Quality checks run INSIDE the pipeline, before a release is finalized. A hard
failure blocks the load (no observations are inserted, so `is_latest` is never
disturbed) and is recorded in `ingestion_log`. Continuity issues are reported as
INFO, not failures.

Every rule carries its rationale in a comment. Rules are deliberately generous —
they exist to catch gross errors (a misplaced decimal, a 250% literacy rate), not
to second-guess legitimate but unusual values. Tighten or loosen with a comment.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# Percentage indicators that are CHANGE/GROWTH rates: they can be negative and are
# bounded tightly, unlike share/level percentages.
GROWTH_RATE_CODES = {"GDP_GROWTH", "POP_GROWTH", "CPI_YOY", "CENSUS_POP_GROWTH"}

# Hand-curated percentage indicators verified to be bounded shares — a share of a
# total, a % of GDP, or an enrolment ratio — that legitimately sit within
# [-10, 200]. The tight band applies ONLY to these known codes, so it catches a
# gross error (a 250% literacy rate) without touching the full WB catalogue, where
# a percentage may be an unbounded growth rate, balance or ratio (see the PCT
# branch in _range_failure). Auto-catalogue percentages are never assumed bounded.
BOUNDED_SHARE_CODES = {
    "ADULT_LITERACY",
    "SCHOOL_ENROLL_PRIMARY",
    "UNEMPLOYMENT",
    "REMITTANCES_GDP",
    "EXPORTS_GDP",
    "IMPORTS_GDP",
    "URBAN_POP_PCT",
    "ELECTRICITY_ACCESS",
    "INTERNET_USERS",
    "CENSUS_LITERACY_RATE",
}

# Hard limits implied by the UNIT ITSELF, for the unit classes the full WB
# catalogue introduced (P2B.S3b). Each is true by definition, so it cannot
# reject legitimate data: a week has 168 hours; a woman cannot bear 50 children;
# pure alcohol per head cannot reach a bathtub. Units whose range depends on
# which indicator you are looking at are deliberately absent — see _range_failure.
UNIT_BOUNDS: dict[str, tuple[Decimal, Decimal]] = {
    "BIRTHS_PER_WOMAN": (Decimal(0), Decimal(20)),
    "HOURS_PER_WEEK": (Decimal(0), Decimal(168)),
    "LITRES_PER_CAPITA": (Decimal(0), Decimal(1000)),
    "MM_PER_YEAR": (Decimal(0), Decimal(20000)),  # world record annual rainfall ~26m
    "UG_PER_M3": (Decimal(0), Decimal(10000)),
    "KG_PER_HECTARE": (Decimal(0), Decimal(1000000)),
    "HECTARES_PER_PERSON": (Decimal(0), Decimal(10000)),
    "PER_KM2": (Decimal(0), Decimal(10) ** 6),
    "MONTHS_OF_IMPORTS": (Decimal(0), Decimal(1200)),  # 100 years of import cover
}


@dataclass(frozen=True)
class Candidate:
    """One value about to be loaded, with the metadata the gate needs to judge it."""

    indicator_id: int | None
    indicator_code: str
    unit_id: int
    unit_code: str
    period_id: int | None
    year: int
    value: Decimal


@dataclass
class QualityResult:
    passed: bool
    failures: list[str]
    infos: list[str]


def run_quality_gate(candidates: list[Candidate]) -> QualityResult:
    failures: list[str] = []

    for c in candidates:
        # (c) Every observation must resolve to a real indicator/geography/period.
        #     Foreign keys already guarantee this, but we assert and report anyway.
        if c.indicator_id is None or c.period_id is None:
            failures.append(f"{c.indicator_code} {c.year}: unresolved indicator/period reference")
            continue
        # (e) No value may come from a non-numeric source string.
        if not c.value.is_finite():
            failures.append(f"{c.indicator_code} {c.year}: value {c.value} is not a finite number")
            continue
        # (a)/(b) Range checks by indicator kind.
        message = _range_failure(c)
        if message is not None:
            failures.append(message)

    # (d) Per-indicator series continuity — reported as INFO, never a failure.
    infos = _continuity_infos(candidates)

    return QualityResult(passed=not failures, failures=failures, infos=infos)


def _range_failure(c: Candidate) -> str | None:
    value = c.value

    # (b) Population: strictly positive and within an order-of-magnitude band.
    #     Nepal's population (~9M in 1960 to ~30M today) sits well inside [1e6, 1e8].
    if c.indicator_code == "POP_TOTAL":
        if not (Decimal(10) ** 6 <= value <= Decimal(10) ** 8):
            return f"{c.indicator_code} {c.year} = {value} outside population band [1e6, 1e8]"
        return None

    # (b') Census population counts run down to district level, where legitimate
    #      values span Manang (~5.6k) to the national total (~29.2M): positive,
    #      capped at 40M (comfortably above Nepal's total — catches a misplaced
    #      decimal or a concatenated number, not real data).
    if c.indicator_code == "CENSUS_POP_TOTAL":
        if not (Decimal(1) <= value <= Decimal(4) * Decimal(10) ** 7):
            return f"{c.indicator_code} {c.year} = {value} outside census population band [1, 4e7]"
        return None

    # (b'') Sex ratio (males per 100 females): human populations sit near 100;
    #       [50, 150] is far wider than any real Nepali geography yet rejects a
    #       percentage or a count accidentally routed here.
    if c.indicator_code == "CENSUS_SEX_RATIO":
        if not (Decimal(50) <= value <= Decimal(150)):
            return f"{c.indicator_code} {c.year} = {value} outside sex-ratio band [50, 150]"
        return None

    # (b''') Density (persons/km²): Manang ~2 to Kathmandu ~5.2k; 25k headroom
    #        allows any plausible urban district while catching unit errors.
    if c.indicator_code == "CENSUS_POP_DENSITY":
        if not (Decimal(0) < value <= Decimal(25000)):
            return f"{c.indicator_code} {c.year} = {value} outside density band (0, 25000]"
        return None

    if c.unit_code == "PCT":
        if c.indicator_code in GROWTH_RATE_CODES:
            # (a) The named national aggregates (GDP/population/CPI growth) are
            #     known-stable series: within +/- 50 %. Crises rarely exceed this,
            #     so a value beyond it signals a parsing error for THESE codes.
            if not (Decimal(-50) <= value <= Decimal(50)):
                return f"{c.indicator_code} {c.year} = {value}% outside growth range [-50, 50]"
            return None
        if c.indicator_code in BOUNDED_SHARE_CODES:
            # (a) Share/level percentages: generous [-10, 200]. The upper bound
            #     allows gross enrolment ratios (legitimately >100) while still
            #     rejecting a gross error such as a 250% literacy rate.
            if not (Decimal(-10) <= value <= Decimal(200)):
                return f"{c.indicator_code} {c.year} = {value}% outside percentage range [-10, 200]"
            return None
        # (a) Every other percentage in the full WB catalogue: annual growth rates
        #     (WDI '_ZG', e.g. CO2 emissions +1497% off a tiny base), signed
        #     balances (external/current-account balance ~ -35% of GDP for Nepal's
        #     chronic trade deficit), and ratios of independent bases (reserves as
        #     ~1116% of debt, tariff peaks ~918%). None of these has a share-like
        #     bound, so a tight band would reject legitimate data (rule #1). The
        #     wide band here is only an order-of-magnitude unit-misrouting guard —
        #     a value beyond it means a count or monetary level was mislabelled PCT
        #     by the auto-catalogue, not a real percentage.
        if not (Decimal(-1000) <= value <= Decimal(5000)):
            return (
                f"{c.indicator_code} {c.year} = {value}% outside "
                f"percentage sanity range [-1000, 5000]"
            )
        return None

    if c.unit_code == "YEARS":
        # Life expectancy: a human plausibility band.
        if not (Decimal(0) <= value <= Decimal(120)):
            return f"{c.indicator_code} {c.year} = {value} outside years range [0, 120]"
        return None

    if c.unit_code == "PER_1000_LIVE_BIRTHS":
        # A rate per 1,000 cannot exceed 1,000.
        if not (Decimal(0) <= value <= Decimal(1000)):
            return f"{c.indicator_code} {c.year} = {value} outside per-1000 range [0, 1000]"
        return None

    # Bands for the unit classes the full WB catalogue introduced (P2B.S3b).
    # Every bound here is true BY DEFINITION of the unit, not a judgement about
    # any indicator: a week has 168 hours, a fertility rate counts children per
    # woman. They catch a unit mix-up or a parsing error without second-guessing
    # legitimate data. Units whose plausible range genuinely depends on the
    # indicator (SCORE, INDEX, RATIO, COUNT, the PER_* family, all monetary and
    # physical quantities) deliberately get NO band — inventing one would be a
    # guess, and a false sense of assurance.
    bounds = UNIT_BOUNDS.get(c.unit_code)
    if bounds is not None:
        low, high = bounds
        if not (low <= value <= high):
            return (
                f"{c.indicator_code} {c.year} = {value} outside "
                f"{c.unit_code} range [{low}, {high}]"
            )
        return None

    # Monetary (USD) and other values: no fixed bound — FDI can be negative, GDP
    # spans many orders of magnitude. Finiteness was already checked above.
    return None


def _continuity_infos(candidates: list[Candidate]) -> list[str]:
    years_by_indicator: dict[str, list[int]] = {}
    for c in candidates:
        years_by_indicator.setdefault(c.indicator_code, []).append(c.year)

    infos: list[str] = []
    for code, years in sorted(years_by_indicator.items()):
        present = set(years)
        lo, hi = min(years), max(years)
        gaps = [y for y in range(lo, hi + 1) if y not in present]
        if gaps:
            infos.append(f"{code}: {len(gaps)} missing year(s) between {lo} and {hi}")
    return infos
