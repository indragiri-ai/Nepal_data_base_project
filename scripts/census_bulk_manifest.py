"""Generate the reviewable manifest for bulk NPHC 2021 CSV ingestion.

This is a metadata compiler, not an ingestion pipeline. It scans the source
headers and dimension domains, then writes:

* ``reference/census/census_bulk_manifest.json`` — exact per-file layouts.
* ``db/seeds/indicators_census_bulk.csv`` — permanent indicator references.

No database or raw-lake writes occur here. Ambiguous layouts fail loudly.
Generated indicator names deliberately retain source table/column vocabulary;
the compiler never invents a meaning for an opaque NSO code.

    make census-bulk-manifest
"""

from __future__ import annotations

import csv
import json
import re
import sys
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ingestion.common.io_utf8 import configure_stdout_utf8

SOURCE_DIR = Path("Census_data")
MANIFEST_PATH = Path("reference/census/census_bulk_manifest.json")
SEED_PATH = Path("db/seeds/indicators_census_bulk.csv")
EXCLUDED_STEMS = {
    "Hhld05_FloorOfHouse",
    "Hhld06_SourceOfDrinkingWater",
    "Indv01_PopulationBySex",
}
SEED_COLUMNS = (
    "code",
    "name_en",
    "definition_en",
    "unit_code",
    "topic",
    "source_concept",
)
TOTAL_LABEL_MARKERS = ("total", "all ", "all_", "both sex")


class ManifestError(Exception):
    """A source layout could not be compiled without guessing."""


@dataclass(frozen=True)
class IndicatorSpec:
    code: str
    name_en: str
    definition_en: str
    unit_code: str
    topic: str
    source_concept: str
    measure: str
    split_values: dict[str, str]


@dataclass(frozen=True)
class FileSpec:
    stem: str
    source_csv: str
    header_line: int
    header: list[str]
    has_gapa: bool
    dimension_columns: list[str]
    split_dimensions: list[str]
    total_dimension_values: dict[str, str]
    label_columns: list[str]
    measure_columns: list[str]
    row_count: int
    indicator_specs: list[IndicatorSpec]


def _is_decimal(raw: str) -> bool:
    if raw.strip() == "":
        return True
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return False
    return value.is_finite()


def _read_table(path: Path) -> tuple[int, list[str], list[list[str]]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        rows = list(reader)
    for index, row in enumerate(rows):
        if len(row) >= 2 and row[0].strip() == "prov" and row[1].strip() == "dist":
            header = [cell.strip() for cell in row]
            while header and header[-1] == "":
                header.pop()
            data_rows = [
                data[: len(header)]
                for data in rows[index + 1 :]
                if data and any(cell.strip() for cell in data)
            ]
            if not data_rows:
                raise ManifestError(f"{path.name}: header found but no data rows")
            if any(len(row) != len(header) for row in data_rows):
                bad = next(row for row in data_rows if len(row) != len(header))
                raise ManifestError(
                    f"{path.name}: data width {len(bad)} does not match header {len(header)}"
                )
            return index + 1, header, data_rows
    raise ManifestError(f"{path.name}: no prov,dist header row found")


def _find_measure_start(
    path: Path,
    header: list[str],
    data_rows: list[list[str]],
    label_anchor: int,
) -> int:
    sample = data_rows[: min(100, len(data_rows))]
    for start in range(label_anchor + 1, len(header)):
        if all(
            _is_decimal(row[column])
            for row in sample
            for column in range(start, len(header))
        ):
            return start
    raise ManifestError(f"{path.name}: could not locate the numeric measure block")


def _table_id(stem: str) -> str:
    match = re.match(r"([A-Za-z]+\d+)", stem)
    if match is None:
        raise ManifestError(f"{stem}: filename has no stable table identifier")
    return match.group(1).upper()


def _safe_code_part(raw: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", raw).strip("_").upper()
    if not value:
        raise ManifestError(f"empty indicator-code component from {raw!r}")
    return value


def _topic_for(stem: str) -> str:
    name = stem.casefold()
    if any(
        token in name
        for token in ("literacy", "edu", "school", "fieldofeducat")
    ):
        return "education"
    if any(
        token in name
        for token in (
            "work",
            "occupation",
            "industry",
            "employment",
            "ecoactivity",
            "sector",
            "reasonnotactive",
        )
    ):
        return "labor"
    if "smallscalebusiness" in name:
        return "economy"
    if any(
        token in name
        for token in (
            "death",
            "disability",
            "drinkingwater",
            "cookingfuel",
            "toilet",
            "facility",
            "foundation",
            "outerwall",
            "roofofhouse",
            "floorofhouse",
            "lighting",
        )
    ):
        return "health"
    return "population"


def _unit_for(stem: str, measure: str) -> str:
    table_id = _table_id(stem)
    measure_lower = measure.casefold()
    if table_id == "INDV02" or table_id == "INDV06":
        return "HOUSEHOLDS"
    if table_id == "INDV05":
        if measure_lower == "numlocality":
            return "COUNT"
        if measure_lower == "nohhld":
            return "HOUSEHOLDS"
        return "PERSONS"
    if table_id.startswith("HHLD"):
        number_match = re.search(r"\d+", table_id)
        if number_match is None:
            raise ManifestError(f"{stem}: household table number is missing")
        number = int(number_match.group())
        if number <= 12:
            return "HOUSEHOLDS"
        if number == 13:
            return "HOUSEHOLDS" if "hhld" in measure_lower else "PERSONS"
        if number == 17:
            return "HOUSEHOLDS" if "hhld" in measure_lower else "PERSONS"
        return "PERSONS"
    return "PERSONS"


def _title_from_stem(stem: str) -> str:
    raw = re.sub(r"^[A-Za-z]+\d+_", "", stem)
    words = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", raw).replace("_", " ")
    return re.sub(r"\s+", " ", words).strip()


def _is_total_label(raw: str) -> bool:
    label = raw.strip().casefold()
    return bool(label) and any(marker in label for marker in TOTAL_LABEL_MARKERS)


def _total_dimension_values(
    header: list[str],
    rows: list[list[str]],
    dimensions: list[str],
    label_columns: list[str],
) -> dict[str, str]:
    if not dimensions:
        return {}
    dimension_indexes = {name: header.index(name) for name in dimensions}
    label_indexes = {name: header.index(name) for name in label_columns}
    totals: dict[str, str] = {}

    # Most tables align dimensions and their published label columns by
    # position (sex -> sexname, agegrp -> agegrpname, occ1 -> occname).
    if len(dimensions) == len(label_columns):
        for dimension, label_column in zip(dimensions, label_columns, strict=True):
            values = {
                row[dimension_indexes[dimension]].strip()
                for row in rows
                if _is_total_label(row[label_indexes[label_column]])
                and row[dimension_indexes[dimension]].strip()
            }
            if len(values) == 1:
                totals[dimension] = next(iter(values))

    # Some two-code tables publish one combined label (litsts+edulvl ->
    # educationlevel). A row whose complete label block says Total identifies
    # the source's total-code tuple without assuming that it is zero.
    if label_columns:
        total_rows = [
            row
            for row in rows
            if all(
                _is_total_label(row[label_indexes[label]])
                for label in label_columns
            )
        ]
        for dimension in dimensions:
            if dimension in totals:
                continue
            values = {
                row[dimension_indexes[dimension]].strip()
                for row in total_rows
                if row[dimension_indexes[dimension]].strip()
            }
            if len(values) == 1:
                totals[dimension] = next(iter(values))

    # A few source tables omit a dimension-label column but use -1 for their
    # aggregate row. This is accepted only because -1 is directly observed.
    for dimension in dimensions:
        if dimension in totals:
            continue
        domain = {
            row[dimension_indexes[dimension]].strip()
            for row in rows
        }
        if "-1" in domain:
            totals[dimension] = "-1"
    return totals


def compile_file(path: Path) -> FileSpec:
    header_line, header, rows = _read_table(path)
    if "provname" not in header or "dname" not in header:
        raise ManifestError(f"{path.name}: required geography label columns missing")
    has_gapa = "gapa" in header
    geo_code_anchor = header.index("gapa") if has_gapa else header.index("dist")
    provname_index = header.index("provname")
    if provname_index <= geo_code_anchor:
        raise ManifestError(f"{path.name}: geography columns are out of order")
    dimensions = header[geo_code_anchor + 1 : provname_index]
    label_anchor_name = "gapaname" if has_gapa else "dname"
    label_anchor = header.index(label_anchor_name)
    measure_start = _find_measure_start(path, header, rows, label_anchor)
    label_columns = header[label_anchor + 1 : measure_start]
    measures = header[measure_start:]
    if not measures:
        raise ManifestError(f"{path.name}: no numeric measures found")

    total_dimension_values = _total_dimension_values(
        header,
        rows,
        dimensions,
        label_columns,
    )
    split_dimensions = [
        name for name in dimensions if name not in total_dimension_values
    ]
    split_indexes = [header.index(name) for name in split_dimensions]
    split_combinations = sorted(
        {
            tuple(row[index].strip() for index in split_indexes)
            for row in rows
        }
    )
    if not split_combinations:
        split_combinations = [()]

    table_id = _table_id(path.stem)
    table_title = _title_from_stem(path.stem)
    specs: list[IndicatorSpec] = []
    for measure in measures:
        for split_combination in split_combinations:
            split_values = dict(zip(split_dimensions, split_combination, strict=True))
            try:
                code_parts = ["CENSUS", table_id, _safe_code_part(measure)]
                for dimension, value in split_values.items():
                    code_parts.extend(
                        (_safe_code_part(dimension), _safe_code_part(value))
                    )
            except ManifestError as exc:
                raise ManifestError(
                    f"{path.name}: invalid indicator component for "
                    f"measure={measure!r}, split={split_values}: {exc}"
                ) from exc
            code = "_".join(code_parts)
            split_note = (
                " "
                + ", ".join(f"{key}={value}" for key, value in split_values.items())
                if split_values
                else ""
            )
            name_en = f"{table_title}: {measure}{split_note} (Census 2021)"
            definition_en = (
                f"Source column {measure} from {path.name}, National Population and "
                "Housing Census 2021. Source dimension labels and codes are preserved "
                "in observation breakdowns; opaque source vocabulary is not guessed."
            )
            source_concept = f"{path.stem}:{measure}"
            if split_values:
                source_concept += "|" + "|".join(
                    f"{key}={value}" for key, value in split_values.items()
                )
            specs.append(
                IndicatorSpec(
                    code=code,
                    name_en=name_en,
                    definition_en=definition_en,
                    unit_code=_unit_for(path.stem, measure),
                    topic=_topic_for(path.stem),
                    source_concept=source_concept,
                    measure=measure,
                    split_values=split_values,
                )
            )

    return FileSpec(
        stem=path.stem,
        source_csv=path.as_posix(),
        header_line=header_line,
        header=header,
        has_gapa=has_gapa,
        dimension_columns=dimensions,
        split_dimensions=split_dimensions,
        total_dimension_values=total_dimension_values,
        label_columns=label_columns,
        measure_columns=measures,
        row_count=len(rows),
        indicator_specs=specs,
    )


def compile_manifest() -> tuple[list[FileSpec], list[str]]:
    specs: list[FileSpec] = []
    failures: list[str] = []
    for path in sorted(SOURCE_DIR.glob("*.csv")):
        if path.stem in EXCLUDED_STEMS:
            continue
        try:
            specs.append(compile_file(path))
        except ManifestError as exc:
            failures.append(str(exc))
    codes = [indicator.code for spec in specs for indicator in spec.indicator_specs]
    duplicates = sorted({code for code in codes if codes.count(code) > 1})
    if duplicates:
        failures.append(f"duplicate generated indicator codes: {duplicates[:10]}")
    return specs, failures


def write_outputs(specs: list[FileSpec]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "source": "National Population and Housing Census 2021 bulk CSVs",
        "excluded_already_loaded": sorted(EXCLUDED_STEMS),
        "files": [asdict(spec) for spec in specs],
    }
    MANIFEST_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    rows = [
        {
            key: getattr(indicator, key)
            for key in SEED_COLUMNS
        }
        for spec in specs
        for indicator in spec.indicator_specs
    ]
    with SEED_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SEED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    configure_stdout_utf8()
    specs, failures = compile_manifest()
    if failures:
        print("FAILED — manifest was not written; ambiguous layouts:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    write_outputs(specs)
    indicators = sum(len(spec.indicator_specs) for spec in specs)
    observations = sum(
        spec.row_count * len(spec.measure_columns)
        for spec in specs
    )
    print(
        f"Compiled {len(specs)} files, {indicators} indicators, "
        f"{observations:,} source cells."
    )
    print(f"Manifest: {MANIFEST_PATH}")
    print(f"Seed CSV: {SEED_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
