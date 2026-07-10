"""Layout knowledge for NRB "Banking and Financial Statistics — Monthly" (BFS).

This module is PURE (no I/O, no openpyxl): it knows what table C4
("Major Financial Indicators") looks like and how to turn its cell values into
canonical (indicator, bfi_class, value) triples. The extractor feeds it a plain
matrix of cell values; tests feed it fixture matrices offline.

Evidence base (never guessed — Prime Directive 7): a scan of ALL 59 monthly
files NRB published between Ashadh 2078 (Mid-July 2021) and Baisakh 2083
(Mid-May 2026) found exactly 35 distinct row labels after normalization, listed
in REGISTRY below. C4's shape is identical in every file:

    row 3      "as on <BS month> End, <BS year> (Mid-<Month>, <year>)"
    row 4      column headers:  D=Class "A"  E=Class "B"  F=Class "C"  G=Overall
    rows 5+    sections A..E; indicator rows have the label in column C and
               numeric values in columns D..G (section E uses only column D,
               which is the commercial-banks column — the interest rates NRB
               reports there are commercial-bank rates, cf. table C15/C20).

Label wobble across years is footnote markers and spacing only (e.g.
"NPL/ Total Loan^" vs "NPL/ Total Loan"), which normalize_label() strips.
The one real trap: "CCD Ratio" (credit to core-capital-plus-deposit, abolished
2022) and "CD Ratio" (credit to deposit, its replacement) are DIFFERENT
regulatory concepts and stay separate indicators.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Bikram Sambat month names, with every romanization NRB has used.
# ---------------------------------------------------------------------------

BS_MONTH_NAMES: dict[str, int] = {
    "baisakh": 1, "baishakh": 1, "baishak": 1,
    "jestha": 2, "jeth": 2, "jyestha": 2,
    "ashadh": 3, "asar": 3, "asadh": 3, "ashad": 3, "ashar": 3,
    "shrawan": 4, "srawan": 4, "sawan": 4, "saun": 4, "shravan": 4,
    "bhadra": 5, "bhadau": 5,
    "ashwin": 6, "aswin": 6, "asoj": 6, "aswhin": 6,
    "kartik": 7, "karttik": 7, "kattik": 7,
    "mangsir": 8, "mangshir": 8, "marga": 8, "margashirsha": 8,
    "poush": 9, "push": 9, "paush": 9, "pus": 9,
    "magh": 10, "mag": 10,
    "falgun": 11, "phagun": 11, "fagun": 11, "phalgun": 11,
    "chaitra": 12, "chait": 12,
}

BS_MONTH_CANONICAL = [
    "Baisakh", "Jestha", "Ashadh", "Shrawan", "Bhadra", "Ashwin",
    "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra",
]

# "as on Baisakh End, 2083 (Mid-May, 2026)" / "as on Asar End, 2078 ..."
_PERIOD_RE = re.compile(r"as\s+on\s+([A-Za-z]+)\s+End\s*,?\s+(\d{4})", re.IGNORECASE)


def parse_period(text: str) -> tuple[int, int] | None:
    """Extract (bs_year, bs_month) from C4's title line. None if not found."""
    m = _PERIOD_RE.search(text)
    if not m:
        return None
    month = BS_MONTH_NAMES.get(m.group(1).casefold())
    if month is None:
        return None
    return int(m.group(2)), month


# ---------------------------------------------------------------------------
# Label normalization: strip everything but letters. Footnote markers (*, #,
# $, ^), spacing and punctuation vary across months; the letters never do.
# ---------------------------------------------------------------------------


def normalize_label(label: Any) -> str:
    return re.sub(r"[^a-z]", "", str(label).casefold())


# ---------------------------------------------------------------------------
# The indicator registry: normalized C4 label -> canonical indicator.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BfsIndicator:
    code: str            # permanent portal code, e.g. 'NRB_BFS_NPL_RATIO'
    name_en: str
    definition_en: str
    unit_code: str       # 'PCT' or 'COUNT'
    section: str         # C4 section heading it lives under


def _pct(code: str, name: str, definition: str, section: str) -> BfsIndicator:
    return BfsIndicator(code, name, definition, "PCT", section)


def _count(code: str, name: str, definition: str, section: str) -> BfsIndicator:
    return BfsIndicator(code, name, definition, "COUNT", section)


_SEC_A = "Credit & deposit ratios"
_SEC_B = "Liquidity ratios"
_SEC_C = "Capital adequacy ratios"
_SEC_D = "Financial access"
_SEC_E = "Interest rates"

_DEF_SUFFIX = (
    " Source: NRB Banking and Financial Statistics (Monthly), table C4"
    " 'Major Financial Indicators'. Provisional figures based on unaudited"
    " returns of banks and financial institutions."
)

REGISTRY: dict[str, BfsIndicator] = {
    # --- Section A: Credit, Deposit Ratios (%) ---
    "totaldepositgdp": _pct(
        "NRB_BFS_DEPOSIT_TO_GDP", "Total deposits to GDP",
        "Total deposits of banks and financial institutions as a share of nominal GDP."
        + _DEF_SUFFIX, _SEC_A),
    "totalcreditgdp": _pct(
        "NRB_BFS_CREDIT_TO_GDP", "Total credit to GDP",
        "Total credit of banks and financial institutions as a share of nominal GDP."
        + _DEF_SUFFIX, _SEC_A),
    "totalcredittotaldeposit": _pct(
        "NRB_BFS_CREDIT_TO_DEPOSIT", "Total credit to total deposits",
        "Total credit as a share of total deposits." + _DEF_SUFFIX, _SEC_A),
    "cdratio": _pct(
        "NRB_BFS_CD_RATIO", "CD ratio (regulatory)",
        "Regulatory credit-to-deposit ratio, month end. Replaced the CCD ratio from 2022."
        + _DEF_SUFFIX, _SEC_A),
    "ccdratio": _pct(
        "NRB_BFS_CCD_RATIO", "CCD ratio (regulatory, discontinued)",
        "Regulatory credit to core-capital-plus-deposit ratio, month end. Abolished in 2022"
        " and replaced by the CD ratio — a DIFFERENT concept kept as a separate series."
        + _DEF_SUFFIX, _SEC_A),
    "fixeddeposittotaldeposit": _pct(
        "NRB_BFS_FIXED_DEPOSIT_SHARE", "Fixed deposits share",
        "Fixed deposits as a share of total deposits." + _DEF_SUFFIX, _SEC_A),
    "savingdeposittotaldeposit": _pct(
        "NRB_BFS_SAVING_DEPOSIT_SHARE", "Saving deposits share",
        "Saving deposits as a share of total deposits." + _DEF_SUFFIX, _SEC_A),
    "currentdeposittotaldeposit": _pct(
        "NRB_BFS_CURRENT_DEPOSIT_SHARE", "Current deposits share",
        "Current deposits as a share of total deposits." + _DEF_SUFFIX, _SEC_A),
    "calldeposittotaldeposit": _pct(
        "NRB_BFS_CALL_DEPOSIT_SHARE", "Call deposits share",
        "Call deposits as a share of total deposits." + _DEF_SUFFIX, _SEC_A),
    "npltotalloan": _pct(
        "NRB_BFS_NPL_RATIO", "Non-performing loans ratio",
        "Non-performing loans as a share of total loans." + _DEF_SUFFIX, _SEC_A),
    "totalllptotalloan": _pct(
        "NRB_BFS_LLP_RATIO", "Loan loss provision ratio",
        "Total loan loss provision as a share of total loans." + _DEF_SUFFIX, _SEC_A),
    "deprivedsectorloantotalloan": _pct(
        "NRB_BFS_DEPRIVED_SECTOR_RATIO", "Deprived sector lending ratio",
        "Deprived sector loans as a share of total loans (6 months prior)."
        + _DEF_SUFFIX, _SEC_A),
    # --- Section B: Liquidity Ratios (%) ---
    "cashbankbalancetotaldeposit": _pct(
        "NRB_BFS_CASH_TO_DEPOSIT", "Cash and bank balance to deposits",
        "Cash and bank balance (incl. money at call) as a share of total deposits."
        + _DEF_SUFFIX, _SEC_B),
    "investmentingovsecuritiestotaldeposit": _pct(
        "NRB_BFS_GOVSEC_TO_DEPOSIT", "Government securities to deposits",
        "Investment in government securities as a share of total deposits."
        + _DEF_SUFFIX, _SEC_B),
    "totalliquidassetstotaldeposit": _pct(
        "NRB_BFS_LIQUID_ASSETS_TO_DEPOSIT", "Liquid assets to deposits",
        "Total liquid assets as a share of total deposits. NRB revised the calculation"
        " method in 2025 (liquid assets exclude balances held with other BFIs)."
        + _DEF_SUFFIX, _SEC_B),
    # --- Section C: Capital Adequacy Ratios (%) ---
    "corecapitalrwa": _pct(
        "NRB_BFS_CORE_CAPITAL_RWA", "Core capital to risk-weighted assets",
        "Core (tier-1) capital as a share of risk-weighted assets." + _DEF_SUFFIX, _SEC_C),
    "totalcapitalrwa": _pct(
        "NRB_BFS_TOTAL_CAPITAL_RWA", "Total capital to risk-weighted assets",
        "Total capital as a share of risk-weighted assets." + _DEF_SUFFIX, _SEC_C),
    # --- Section D: Financial Access (counts) ---
    "noofinstitutions": _count(
        "NRB_BFS_INSTITUTIONS", "Number of institutions",
        "Number of NRB-licensed banks and financial institutions." + _DEF_SUFFIX, _SEC_D),
    "noofbranches": _count(
        "NRB_BFS_BRANCHES", "Number of branches",
        "Number of branches (including head offices)." + _DEF_SUFFIX, _SEC_D),
    "noofdepositaccounts": _count(
        "NRB_BFS_DEPOSIT_ACCOUNTS", "Number of deposit accounts",
        "Number of deposit accounts." + _DEF_SUFFIX, _SEC_D),
    "noofloanaccounts": _count(
        "NRB_BFS_LOAN_ACCOUNTS", "Number of loan accounts",
        "Number of loan accounts." + _DEF_SUFFIX, _SEC_D),
    "noofbranchlessbankingcenters": _count(
        "NRB_BFS_BRANCHLESS_CENTERS", "Branchless banking centers",
        "Number of branchless banking centers." + _DEF_SUFFIX, _SEC_D),
    "noofbranchlessbankingcustomers": _count(
        "NRB_BFS_BRANCHLESS_CUSTOMERS", "Branchless banking customers",
        "Number of branchless banking customers." + _DEF_SUFFIX, _SEC_D),
    "noofmobilebankingcustomers": _count(
        "NRB_BFS_MOBILE_BANKING_USERS", "Mobile banking customers",
        "Number of mobile banking customers." + _DEF_SUFFIX, _SEC_D),
    "noofinternetbankingcustomers": _count(
        "NRB_BFS_INTERNET_BANKING_USERS", "Internet banking customers",
        "Number of internet banking customers." + _DEF_SUFFIX, _SEC_D),
    "noofatms": _count(
        "NRB_BFS_ATMS", "Number of ATMs",
        "Number of automated teller machines." + _DEF_SUFFIX, _SEC_D),
    "noofdebitcards": _count(
        "NRB_BFS_DEBIT_CARDS", "Number of debit cards",
        "Number of debit cards issued." + _DEF_SUFFIX, _SEC_D),
    "noofcreditcards": _count(
        "NRB_BFS_CREDIT_CARDS", "Number of credit cards",
        "Number of credit cards issued." + _DEF_SUFFIX, _SEC_D),
    "noofprepaidcards": _count(
        "NRB_BFS_PREPAID_CARDS", "Number of prepaid cards",
        "Number of prepaid cards issued." + _DEF_SUFFIX, _SEC_D),
    # --- Section E: Interest Rate (%) — commercial-bank rates (column D only) ---
    "wtavginterestrateondeposit": _pct(
        "NRB_BFS_DEPOSIT_RATE", "Weighted average deposit rate",
        "Weighted average interest rate on deposits of commercial banks."
        + _DEF_SUFFIX, _SEC_E),
    "asaving": _pct(
        "NRB_BFS_DEPOSIT_RATE_SAVING", "Weighted average saving deposit rate",
        "Weighted average interest rate on saving deposits of commercial banks."
        + _DEF_SUFFIX, _SEC_E),
    "bfixed": _pct(
        "NRB_BFS_DEPOSIT_RATE_FIXED", "Weighted average fixed deposit rate",
        "Weighted average interest rate on fixed deposits of commercial banks."
        + _DEF_SUFFIX, _SEC_E),
    "ccall": _pct(
        "NRB_BFS_DEPOSIT_RATE_CALL", "Weighted average call deposit rate",
        "Weighted average interest rate on call deposits of commercial banks."
        + _DEF_SUFFIX, _SEC_E),
    "wtavginterestrateoncredit": _pct(
        "NRB_BFS_LENDING_RATE", "Weighted average lending rate",
        "Weighted average interest rate on credit of commercial banks."
        + _DEF_SUFFIX, _SEC_E),
    "wtaveragespreadrate": _pct(
        "NRB_BFS_SPREAD_RATE", "Weighted average interest spread",
        "Weighted average spread between lending and deposit rates of commercial banks."
        + _DEF_SUFFIX, _SEC_E),
}

# Column index (0-based, columns A..G) -> breakdown value for observations.
CLASS_COLUMNS: dict[int, str] = {
    3: "commercial_banks",     # Class "A"
    4: "development_banks",    # Class "B"
    5: "finance_companies",    # Class "C"
    6: "overall",              # Overall
}


# ---------------------------------------------------------------------------
# The C4 parser: matrix of cell values in, canonical triples out.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedValue:
    indicator_code: str
    bfi_class: str
    value: float
    row_label: str      # the label exactly as printed in the file
    section: str
    unit_code: str


@dataclass
class ParsedC4:
    bs_year: int
    bs_month: int
    period_label: str               # C4's own title line, verbatim
    values: list[ParsedValue] = field(default_factory=list)
    unmatched_labels: list[str] = field(default_factory=list)
    skipped_cells: int = 0          # non-numeric cells in value columns


class BfsParseError(Exception):
    """C4 could not be parsed — report, never guess (Prime Directive 7)."""


def parse_c4(rows: list[tuple[Any, ...]]) -> ParsedC4:
    """Parse the cell matrix of sheet C4 (rows of columns A..G, values only).

    Unrecognized labels are collected in `unmatched_labels` — the caller
    decides whether to fail or report. Nothing is ever guessed.
    """
    # 1. The period, from the title line in the first few rows.
    period: tuple[int, int] | None = None
    period_label = ""
    for row in rows[:6]:
        for cell in row:
            if isinstance(cell, str) and (found := parse_period(cell)):
                period, period_label = found, cell.strip()
                break
        if period:
            break
    if not period:
        raise BfsParseError("no 'as on <month> End, <year>' title line found in C4")

    parsed = ParsedC4(bs_year=period[0], bs_month=period[1], period_label=period_label)

    # 2. Indicator rows: label in column C (index 2), values in D..G.
    for row in rows:
        label = row[2] if len(row) > 2 else None
        if label is None or not str(label).strip():
            continue
        key = normalize_label(label)
        if not key:
            continue
        spec = REGISTRY.get(key)
        cells = {i: (row[i] if len(row) > i else None) for i in CLASS_COLUMNS}
        has_numbers = any(isinstance(v, (int, float)) for v in cells.values())
        if spec is None:
            if has_numbers:  # a data row we don't know — report it
                parsed.unmatched_labels.append(str(label).strip())
            continue
        if not has_numbers:
            continue
        for col, bfi_class in CLASS_COLUMNS.items():
            v = cells[col]
            if isinstance(v, (int, float)):
                parsed.values.append(ParsedValue(
                    indicator_code=spec.code, bfi_class=bfi_class, value=float(v),
                    row_label=str(label).strip(), section=spec.section,
                    unit_code=spec.unit_code,
                ))
            elif v is not None and str(v).strip():
                parsed.skipped_cells += 1

    if not parsed.values:
        raise BfsParseError("C4 title parsed but no indicator rows matched the registry")
    return parsed
