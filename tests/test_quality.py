"""Tests for the in-pipeline data-quality gate (P1.S9). Pure logic — no network."""

from __future__ import annotations

from decimal import Decimal

from ingestion.common.quality import Candidate, run_quality_gate


def _c(code: str, unit: str, year: int, value: str, *, ind_id: int | None = 1,
       period_id: int | None = 10) -> Candidate:
    return Candidate(
        indicator_id=ind_id,
        indicator_code=code,
        unit_id=1,
        unit_code=unit,
        period_id=period_id,
        year=year,
        value=Decimal(value),
    )


def test_clean_batch_passes() -> None:
    batch = [
        _c("ADULT_LITERACY", "PCT", 2021, "67.9"),
        _c("GDP_GROWTH", "PCT", 2020, "-2.37"),
        _c("POP_TOTAL", "PERSONS", 2021, "29475010"),
        _c("LIFE_EXPECTANCY", "YEARS", 2021, "68.4"),
    ]
    result = run_quality_gate(batch)
    assert result.passed
    assert result.failures == []


def test_impossible_percentage_is_blocked() -> None:
    # The step's example: a 250% literacy rate must be caught.
    result = run_quality_gate([_c("ADULT_LITERACY", "PCT", 2021, "250")])
    assert not result.passed
    assert any("ADULT_LITERACY" in f and "250" in f for f in result.failures)


def test_implausible_growth_rate_is_blocked() -> None:
    result = run_quality_gate([_c("GDP_GROWTH", "PCT", 2020, "999")])
    assert not result.passed


def test_nonpositive_population_is_blocked() -> None:
    result = run_quality_gate([_c("POP_TOTAL", "PERSONS", 2021, "0")])
    assert not result.passed


def test_unresolved_reference_is_blocked() -> None:
    result = run_quality_gate([_c("GDP_USD", "USD", 2021, "12345", period_id=None)])
    assert not result.passed


def test_new_unit_bands_accept_real_values() -> None:
    """The bands added for the full WB catalogue (P2B.S3b) must not reject
    legitimate Nepal data."""
    batch = [
        _c("SP_DYN_TFRT_IN", "BIRTHS_PER_WOMAN", 2023, "1.917"),
        _c("SL_TLF_0714_WK_TM", "HOURS_PER_WEEK", 2011, "24.6"),
        _c("SH_ALC_PCAP_LI", "LITRES_PER_CAPITA", 2019, "2.1"),
        _c("AG_LND_PRCP_MM", "MM_PER_YEAR", 2020, "1500"),
        _c("EN_ATM_PM25_MC_M3", "UG_PER_M3", 2019, "83.1"),
        _c("EN_POP_DNST", "PER_KM2", 2022, "206.9"),
    ]
    result = run_quality_gate(batch)
    assert result.passed, result.failures


def test_new_unit_bands_catch_impossible_values() -> None:
    """Each band is true by definition of the unit, so a violation is a real
    error — a unit mix-up or a parsing failure."""
    for code, unit, value in [
        ("SP_DYN_TFRT_IN", "BIRTHS_PER_WOMAN", "45"),  # no woman bears 45 children
        ("SL_TLF_0714_WK_TM", "HOURS_PER_WEEK", "200"),  # a week has 168 hours
        ("AG_LND_PRCP_MM", "MM_PER_YEAR", "-5"),  # negative rainfall
    ]:
        result = run_quality_gate([_c(code, unit, 2020, value)])
        assert not result.passed, f"{code}={value} should have been blocked"


def test_units_without_a_definitional_range_are_not_second_guessed() -> None:
    """SCORE, INDEX, RATIO and COUNT have no band on purpose: their plausible
    range depends on the indicator, so inventing one would be a guess. The WGI
    governance estimates are genuinely negative."""
    batch = [
        _c("GOV_WGI_CC_EST", "SCORE", 2024, "-0.63"),
        _c("GOV_WGI_RL_SC", "SCORE", 2024, "51.74"),
        _c("SM_POP_NETM", "COUNT", 2023, "-364699"),  # net migration is signed
        _c("SE_PRM_ENRL_TC_ZS", "RATIO", 2023, "19.7"),
    ]
    result = run_quality_gate(batch)
    assert result.passed, result.failures


def test_catalogue_percentages_that_are_not_bounded_shares_pass() -> None:
    """The full WB catalogue (P2B.S3b) adds percentage indicators that are growth
    rates, signed balances and ratios of independent bases — none share-bounded.
    These are the exact real Nepal values the tight [-10, 200] band wrongly blocked;
    they must load. Values verified against data.worldbank.org."""
    batch = [
        _c("EN_GHG_CO2_ZG_AR5", "PCT", 2021, "1497.11503123852"),  # emissions growth, tiny base
        _c("NE_RSB_GNFS_ZS", "PCT", 2022, "-35.5686197495399"),  # external balance, % of GDP
        _c("BN_CAB_XOKA_GD_ZS", "PCT", 2021, "-14.5240163530399"),  # current account balance
        _c("FI_RES_TOTL_DT_ZS", "PCT", 1971, "1116.79526336964"),  # reserves as % of external debt
        _c("TM_TAX_TCOM_WM_AR_ZS", "PCT", 2008, "917.75"),  # tariff weighted mean
        _c("NE_IMP_GNFS_KD_ZG", "PCT", 2020, "-20.8480903733518"),  # real import growth, COVID year
    ]
    result = run_quality_gate(batch)
    assert result.passed, result.failures


def test_catalogue_percentage_wildly_out_of_range_is_blocked() -> None:
    """The wide band on catalogue percentages is still a unit-misrouting guard: a
    population count mislabelled PCT by the auto-catalogue is far beyond it."""
    result = run_quality_gate([_c("SOME_WB_SHARE_ZS", "PCT", 2021, "29475010")])
    assert not result.passed


def test_bounded_share_still_catches_gross_error() -> None:
    """A hand-curated share keeps the tight band: 250% electricity access is a
    parsing error, not real data."""
    result = run_quality_gate([_c("ELECTRICITY_ACCESS", "PCT", 2021, "250")])
    assert not result.passed


def test_year_gaps_are_info_not_failure() -> None:
    batch = [
        _c("CPI_YOY", "PCT", 2018, "4.1"),
        _c("CPI_YOY", "PCT", 2020, "5.0"),  # 2019 missing
    ]
    result = run_quality_gate(batch)
    assert result.passed  # gaps never fail the gate
    assert any("CPI_YOY" in info and "missing" in info for info in result.infos)
