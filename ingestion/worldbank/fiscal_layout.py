"""Layout registry for the WB Nepal Fiscal Dashboard (WBF.S2).

The registry mirrors what the source actually contains — it never forces the
source into a shape we preferred. Every list here was READ from the dashboard
on 2026-08-01 and, where the source publishes a parent total, proven complete
by summing the parts back to it (see `SUM_CHECKS`). A category set that stops
summing to its parent means the source changed and the load must fail, not
quietly drop a category.

Nothing in this module performs I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# --- Geography -------------------------------------------------------------
#
# The dashboard's province spellings, mapped to the warehouse's P-codes. Both
# sides were read on 2026-08-01 and match exactly, so this is a plain 1:1 map
# rather than a normalisation.
#
# The spelling is load-bearing: `Province Name=Sudurpaschim` returns data while
# `Sudurpashchim` returns ZERO ROWS WITH NO ERROR. An unmatched province is
# therefore indistinguishable from "no data" and must fail loudly.
PROVINCE_CODES: dict[str, str] = {
    "Koshi": "NP01",
    "Madhesh": "NP02",
    "Bagmati": "NP03",
    "Gandaki": "NP04",
    "Lumbini": "NP05",
    "Karnali": "NP06",
    "Sudurpaschim": "NP07",
}

FEDERAL_GEO_CODE = "NP"

# --- Time ------------------------------------------------------------------
#
# The dashboard labels a fiscal year by the Gregorian year it ENDS in, so its
# `FY2018` is Nepal's FY 2017/18 (BS 2074/75). This was not assumed — the step
# file flagged the ambiguity, and two independent magnitude checks resolve it:
#
#   1. Federal "FY2018" revenue and grants = NPR 766,036.1 million, of which
#      Grants = 39,318.7. Nepal's FY 2017/18 revenue plus foreign grants is of
#      that order; FY 2018/19 revenue is materially higher (~NPR 859bn), which
#      would not fit.
#   2. The Provincial GDP sheet's "FY 2024" shows agriculture GVA of
#      NPR 1,248,694.4 million (~NPR 1.25 trillion), consistent with Nepal's
#      FY 2023/24 agricultural GVA, not FY 2024/25.
#
# Both point the same way. This remains a DERIVED mapping: WBF.S2's spot-check
# against the MoF Red Book must confirm it before any figure is published, and
# the derivation is recorded in each indicator's definition so it stays
# auditable.
FIRST_DASHBOARD_YEAR = 2018
LAST_DASHBOARD_YEAR = 2024


def dashboard_year_to_period_label(dashboard_year: str) -> str:
    """`FY2018` -> `FY 2017/18` (the warehouse's fiscal-year label).

    Raises ValueError on anything outside the published window rather than
    inventing a period for a label the source did not publish.
    """
    text = dashboard_year.strip().replace(" ", "")
    if not text.upper().startswith("FY"):
        raise ValueError(f"not a dashboard fiscal-year label: {dashboard_year!r}")
    digits = text[2:]
    if not digits.isdigit() or len(digits) != 4:
        raise ValueError(f"not a dashboard fiscal-year label: {dashboard_year!r}")
    end = int(digits)
    if not FIRST_DASHBOARD_YEAR <= end <= LAST_DASHBOARD_YEAR:
        raise ValueError(
            f"{dashboard_year!r} is outside the published window "
            f"FY{FIRST_DASHBOARD_YEAR}-FY{LAST_DASHBOARD_YEAR}"
        )
    return f"FY {end - 1}/{str(end)[2:]}"


# --- Units -----------------------------------------------------------------
#
# Read from the data, never assumed: the provincial and local sheets carry a
# `Local Unit` column whose literal value is `NPR Million`. A 1000x unit error
# is the classic fiscal-data failure, so the loader asserts this string and
# fails if the source ever changes it.
SOURCE_UNIT_LABEL = "NPR Million"
UNIT_CODE = "NPR_MILLION"


# --- Sheets ----------------------------------------------------------------


@dataclass(frozen=True)
class SheetSpec:
    """One dashboard sheet and how its rows become observations."""

    sheet: str  # Tableau sheet name, e.g. "Federal Revenue"
    tier: str  # "federal" | "provincial"
    indicator_code: str  # the parent concept
    parent_label: str  # the Group1/Group2 value carrying the parent total
    categories: tuple[str, ...]  # Group2 values; () = no breakdown published
    types: tuple[str, ...]  # which Type1 values exist for THIS sheet
    topic: str  # warehouse indicator topic


# `types` differs per sheet and was measured, not assumed: Federal Debt Stock
# returns 0 rows for Type1=Budget, so it carries actuals only.
FEDERAL_SHEETS: tuple[SheetSpec, ...] = (
    SheetSpec(
        sheet="Federal Revenue",
        tier="federal",
        indicator_code="FISCAL_REVENUE_TOTAL",
        parent_label="Revenue and grants",
        categories=("Taxes", "Grants", "Other revenue", "Miscellaneous receipt"),
        types=("Actual", "Budget"),
        topic="economy",
    ),
    SheetSpec(
        sheet="Federal Expenditure",
        tier="federal",
        indicator_code="FISCAL_EXPENDITURE_TOTAL",
        parent_label="Expenditure (Economic)",
        categories=("Recurrent expenditure", "Capital expenditure"),
        types=("Actual", "Budget"),
        topic="economy",
    ),
    SheetSpec(
        sheet="Federal Financing",
        tier="federal",
        indicator_code="FISCAL_FINANCING_TOTAL",
        parent_label="Financing",
        categories=(
            "Net acquisition of financial assets",
            "Net incurrence of liabilities",
        ),
        types=("Actual", "Budget"),
        topic="economy",
    ),
    SheetSpec(
        sheet="Federal Debt Stock",
        tier="federal",
        indicator_code="FISCAL_DEBT_STOCK",
        parent_label="Debt stock",
        categories=(),
        types=("Actual",),  # measured: Type1=Budget returns zero rows
        topic="economy",
    ),
    SheetSpec(
        sheet="Federal Fiscal Indicators",
        tier="federal",
        indicator_code="FISCAL_NET_OPERATING_BALANCE",
        parent_label="Net operating balance",
        categories=(),
        types=("Actual", "Budget"),
        topic="economy",
    ),
)

PROVINCIAL_SHEETS: tuple[SheetSpec, ...] = (
    SheetSpec(
        sheet="Provincial Revenue",
        tier="provincial",
        indicator_code="FISCAL_PROV_REVENUE_TOTAL",
        parent_label="Revenue and grants",
        categories=("Taxes", "Grants", "Other revenue", "Miscellaneous receipt"),
        types=("Actual", "Budget"),
        topic="economy",
    ),
    SheetSpec(
        sheet="Provincial Expenditure",
        tier="provincial",
        indicator_code="FISCAL_PROV_EXPENDITURE_TOTAL",
        parent_label="Expenditure (Economic)",
        categories=("Recurrent expenditure", "Capital expenditure"),
        types=("Actual", "Budget"),
        topic="economy",
    ),
    SheetSpec(
        sheet="Provincial Financing",
        tier="provincial",
        indicator_code="FISCAL_PROV_FINANCING_TOTAL",
        parent_label="Financing",
        categories=(
            "Net acquisition of financial assets",
            "Net incurrence of liabilities",
        ),
        types=("Actual", "Budget"),
        topic="economy",
    ),
    SheetSpec(
        sheet="Provincial Fiscal Indicators",
        tier="provincial",
        indicator_code="FISCAL_PROV_NET_OPERATING_BALANCE",
        parent_label="Net operating balance",
        categories=(),
        types=("Actual", "Budget"),
        topic="economy",
    ),
    SheetSpec(
        sheet="Provincial Grants",
        tier="provincial",
        indicator_code="FISCAL_PROV_GRANTS_TOTAL",
        parent_label="Intergovernmental fiscal transfer",
        categories=(
            "Equalization grant",
            "Conditional grant",
            "Complementary grant",
            "Special grant",
            "Other grant",
        ),
        types=("Actual", "Budget"),
        topic="economy",
    ),
)

ALL_SHEETS: tuple[SheetSpec, ...] = FEDERAL_SHEETS + PROVINCIAL_SHEETS


# --- Completeness evidence -------------------------------------------------
#
# Recorded so a future reader can re-run the reasoning rather than trust it.
# Both were exact to the last decimal on 2026-08-01.
SUM_CHECKS: tuple[tuple[str, tuple[Decimal, ...], Decimal], ...] = (
    (
        "7 provinces, Taxes, FY2024 -> all-provinces total",
        (
            Decimal("12320.47"), Decimal("11275.08"), Decimal("20704.84"),
            Decimal("12907.97"), Decimal("11828.10"), Decimal("7766.79"),
            Decimal("8166.11"),
        ),
        Decimal("84969.36"),
    ),
    (
        "Federal revenue categories, FY2018 -> revenue and grants",
        (
            Decimal("640169.3"), Decimal("39318.7"), Decimal("0"),
            Decimal("86548.1"),
        ),
        Decimal("766036.1"),
    ),
)


def parse_amount(raw: str) -> Decimal:
    """`"1,013,490.1"` -> Decimal. Fails loudly on anything unexpected.

    The source formats with thousands separators and uses a bare `0` for a true
    zero. An unparseable cell is a changed source, not a zero — returning 0
    here would silently publish a wrong number.
    """
    text = raw.strip().replace(",", "").replace(" ", "")
    if text in {"", "*", "-", "null", "Null"}:
        raise ValueError(f"not a numeric amount: {raw!r}")
    try:
        return Decimal(text)
    except Exception as exc:  # noqa: BLE001 - re-raised with context
        raise ValueError(f"not a numeric amount: {raw!r}") from exc
