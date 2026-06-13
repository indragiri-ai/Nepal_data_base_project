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
GROWTH_RATE_CODES = {"GDP_GROWTH", "POP_GROWTH", "CPI_YOY"}


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

    if c.unit_code == "PCT":
        if c.indicator_code in GROWTH_RATE_CODES:
            # (a) Growth/change rates: within +/- 50 %. Crises rarely exceed this;
            #     a value beyond it signals a parsing error.
            if not (Decimal(-50) <= value <= Decimal(50)):
                return f"{c.indicator_code} {c.year} = {value}% outside growth range [-50, 50]"
        # (a) Share/level percentages: generous [-10, 200]. The upper bound allows
        #     gross enrolment ratios (legitimately >100) while still rejecting a
        #     gross error such as a 250% literacy rate.
        elif not (Decimal(-10) <= value <= Decimal(200)):
            return f"{c.indicator_code} {c.year} = {value}% outside percentage range [-10, 200]"
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
