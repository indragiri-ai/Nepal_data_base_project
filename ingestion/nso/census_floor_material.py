"""Load NPHC 2021 household floor materials at every geography level.

The six source category codes are preserved verbatim in
``breakdowns["category"]`` so the published column vocabulary remains
traceable without inventing display labels.

    make ingest-census-floor-material
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

from ingestion.nso.census_shape_a import ShapeAConfig, run_shape_a

CATEGORY_COLUMNS = (
    "a_Mud",
    "b_Wooden",
    "c_BrickStone",
    "d_Ceramic",
    "e_Cemented",
    "f_Other",
)

CONFIG = ShapeAConfig(
    indicator_code="CENSUS_HH_FLOOR_MATERIAL",
    source_csv=Path("Census_data/Hhld05_FloorOfHouse.csv"),
    category_columns=CATEGORY_COLUMNS,
    expected_national_total=Decimal("6660841"),
    raw_dataset_path="nso/census2021/households/Hhld05_FloorOfHouse",
    summary_name="Household floor-material",
)


def run() -> int:
    return run_shape_a(CONFIG)


if __name__ == "__main__":
    sys.exit(run())
