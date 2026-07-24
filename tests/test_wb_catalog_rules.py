"""Offline tests for the World Bank catalogue curation rules (P2B.S3a).

These pin the unit/sector rules in `scripts/wb_catalog.py` so a future tweak
cannot silently re-shelve indicators or mis-unit them. No network: the rules are
pure functions of an indicator's name, unit string, code and WB topics.
"""

from __future__ import annotations

import pytest

from scripts.wb_catalog import resolve_sector, resolve_unit


@pytest.mark.parametrize(
    ("name", "unit", "expected"),
    [
        # percentages win over everything else
        ("Current account balance (% of GDP)", "", "PCT"),
        # money, most specific first
        ("GDP per capita, PPP (constant 2021 international $)", "", "USD_PPP"),
        ("GDP per capita (constant 2015 US$)", "", "USD"),
        ("Military expenditure (current USD)", "", "USD"),  # WB writes "USD", not "US$"
        ("Agriculture, forestry, and fishing, value added (current LCU)", "", "LCU"),
        # rate families
        ("Mortality rate, infant (per 1,000 live births)", "", "PER_1000_LIVE_BIRTHS"),
        ("Fertility rate, total (births per woman)", "", "BIRTHS_PER_WOMAN"),
        ("Average working hours of children, ages 7-14 (hours per week)", "", "HOURS_PER_WEEK"),
        # compound physical units resolve before the bare quantity inside them
        ("Cereal yield (kg per hectare)", "", "KG_PER_HECTARE"),
        ("Arable land (hectares per person)", "", "HECTARES_PER_PERSON"),
        ("Average precipitation in depth (mm per year)", "", "MM_PER_YEAR"),
        ("Electric power consumption (kWh per capita)", "", "KWH_PER_CAPITA"),
        ("Annual freshwater withdrawals, total (billion cubic meters)", "", "BILLION_M3"),
        ("Renewable internal freshwater resources per capita (cubic meters)", "", "M3_PER_CAPITA"),
        # bounded scales
        ("Control of Corruption - Governance estimate (approx. -2.5 to +2.5)", "", "SCORE"),
        ("B-READY: Business Entry: Overall Score", "", "SCORE"),
        ("GDP deflator (base year varies by country)", "", "INDEX"),
        # genuine ratios
        ("Pupil-teacher ratio, primary", "", "RATIO"),
        ("Sex ratio at birth (male births per female births)", "", "RATIO"),
        # counts
        ("Refugees under the mandate of the UNHCR by country of asylum", "", "COUNT"),
    ],
)
def test_resolve_unit(name: str, unit: str, expected: str) -> None:
    assert resolve_unit(name, unit) == expected


@pytest.mark.parametrize(
    "name",
    [
        # "ratio" as a bare substring also appears inside these words. Matching it
        # loosely once tagged a -364,699 person net-migration figure as a RATIO.
        "Net migration",
        "Population in urban agglomerations of more than 1 million",
        "B-READY: Taxation Pillar 3: Operational Efficiency of Tax Systems",
    ],
)
def test_ratio_matches_whole_word_only(name: str) -> None:
    assert resolve_unit(name, "") != "RATIO"


def test_unresolvable_unit_is_reported_not_guessed() -> None:
    """An indicator whose unit the rules do not cover must return None so the
    caller writes it to the unmapped report (non-negotiable rule #1)."""
    assert resolve_unit("Arms imports (SIPRI trend indicator values)", "") is None
    assert resolve_unit("Lifetime risk of maternal death (1 in: rate varies)", "") is None


@pytest.mark.parametrize(
    ("code", "topics", "expected"),
    [
        # 1. demography override — WB publishes no "Population" topic
        ("SP.POP.0014.TO.ZS", ("Education",), "population"),
        ("SP.POP.65UP.TO", ("Health",), "population"),
        ("SP.RUR.TOTL", ("Agriculture & Rural Development",), "population"),
        ("SP.URB.GROW", ("Climate Change",), "population"),
        ("SM.POP.NETM", (), "population"),
        ("SP.DYN.TFRT.IN", ("Health",), "population"),
        # ...but health outcomes carrying an SP.DYN code stay in health
        ("SP.DYN.LE00.FE.IN", ("Health",), "health"),
        ("SP.DYN.IMRT.MA.IN", ("Health",), "health"),
        # ...and the two explicit non-demographic exceptions keep WB's topic
        ("SP.POP.SCIE.RD.P6", ("Science & Technology",), "economy"),
        # 2. WB's own topic, when it supplies one
        ("NY.GDP.PCAP.KD", ("Economy & Growth",), "economy"),
        ("SE.SEC.ENRR.FE", ("Education",), "education"),
        ("SL.TLF.ACTI.MA.ZS", ("Social Protection & Labor",), "labor"),
        ("EG.ELC.HYRO.ZS", ("Energy & Mining",), "environment"),
        # 3. code-family fallback, used only when WB gives no topic at all
        ("GOV_WGI_CC_EST", (), "governance"),
        ("GD_WBL_OVL_LAW", (), "governance"),
        ("IC.BRE.BE.OS", (), "economy"),
        ("SI.POV.MPWB", (), "economy"),
        ("SH_UHC_FH40", (), "health"),
        ("HD_HCIP_EDUC_TO", (), "education"),
        ("HD_HCIP_HLTH_TO", (), "health"),
    ],
)
def test_resolve_sector(code: str, topics: tuple[str, ...], expected: str) -> None:
    assert resolve_sector(code, topics) == expected


def test_unknown_topic_is_not_second_guessed_by_the_code_family() -> None:
    """If WB DID classify an indicator and we don't recognise that topic, it goes
    to the unmapped report — the code-family fallback is only for the untopiced."""
    assert resolve_sector("NY.GDP.MKTP.CD", ("Some New WB Topic",)) is None


def test_composite_hci_is_left_unmapped() -> None:
    """The overall HCI score spans the education, health and labor pillars, so it
    is reported rather than forced into one sector."""
    assert resolve_sector("HD_HCIP_OVRL_TO", ()) is None
