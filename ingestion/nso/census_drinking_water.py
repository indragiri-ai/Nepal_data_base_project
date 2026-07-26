"""Load NPHC 2021 household drinking-water sources at every geography level.

The nine source category codes are preserved verbatim because ``TapPiped1`` and
``TapPiped2`` are not self-explanatory and this project never guesses labels.

    make ingest-census-drinking-water
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

from ingestion.nso.census_shape_a import ShapeAConfig, run_shape_a

CATEGORY_COLUMNS = (
    "a_TapPiped1",
    "b_TapPiped2",
    "c_Tubewell",
    "d_CoveredWell",
    "e_UncoverWell",
    "f_Spoutwater",
    "g_RiverStream",
    "h_JarBottle",
    "i_Others",
)

CONFIG = ShapeAConfig(
    indicator_code="CENSUS_HH_DRINKING_WATER",
    source_csv=Path("Census_data/Hhld06_SourceOfDrinkingWater.csv"),
    category_columns=CATEGORY_COLUMNS,
    expected_national_total=Decimal("6660841"),
    raw_dataset_path="nso/census2021/households/Hhld06_SourceOfDrinkingWater",
    summary_name="Household drinking-water",
)


def run() -> int:
    return run_shape_a(CONFIG)


if __name__ == "__main__":
    sys.exit(run())
