"""Offline parse test for the World Bank pipeline (P1.S8).

Uses a saved sample API response so parsing is verified without any network.
"""

from __future__ import annotations

import json
from pathlib import Path

from ingestion.worldbank.pipeline import extract_points

FIXTURE = Path(__file__).parent / "fixtures" / "wb_sample.json"


def test_extract_points_reads_years_and_skips_nulls() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    points = extract_points(payload[1])

    assert len(points) == 3
    by_year = {p.year: p.value for p in points}
    assert by_year[2020] == -2.3696206292072  # the COVID contraction
    assert by_year[2019] == 6.65705543110467
    assert by_year[1960] is None  # null values are preserved as None (rejected at load time)
