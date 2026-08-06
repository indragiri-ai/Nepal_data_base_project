"""ODN.S1 CKAN client tests. Offline: no network, no database.

The fixture is a real captured response from
`datastore_search?resource_id=b791b8cd-…&limit=3` (Kalimati, June 2013), so the
envelope shape being asserted here is the portal's own, not an invention.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ingestion.opendatanepal.ckan_client import (
    CkanError,
    parse_page,
    summarise,
)

FIXTURE = Path(__file__).parent / "fixtures" / "ckan_datastore_page.json"


def _result() -> dict[str, Any]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    result: dict[str, Any] = payload["result"]
    return result


# --- reading a datastore page ------------------------------------------------


def test_the_captured_page_parses_into_total_fields_and_records() -> None:
    total, fields, records = parse_page(_result())
    assert total == 197161
    assert fields == ["_id", "SN", "Commodity", "Date", "Unit", "Minimum", "Maximum", "Average"]
    assert len(records) == 3


def test_the_first_row_is_the_recorded_sample_exactly() -> None:
    """The facts bank's row, verified byte for byte.

    This is the anchor: if the portal ever re-uploads the resource with
    different content, columns or ordering, this fails rather than letting a
    changed source pass as the same one.
    """
    _, _, records = parse_page(_result())
    row = records[0]
    assert row["Commodity"] == "Tomato Big(Nepali)"
    assert row["Date"] == "2013-06-16"
    assert row["Unit"] == "Kg"
    assert row["Minimum"] == "35.0"
    assert row["Maximum"] == "40.0"
    assert row["Average"] == "37.5"


def test_a_page_without_a_total_is_refused() -> None:
    # Without `total` there is no way to know a harvest finished.
    result = _result()
    del result["total"]
    with pytest.raises(CkanError, match="no integer 'total'"):
        parse_page(result)


def test_a_non_integer_total_is_refused() -> None:
    result = _result()
    result["total"] = "197161"
    with pytest.raises(CkanError, match="no integer 'total'"):
        parse_page(result)


def test_a_page_without_records_is_refused() -> None:
    result = _result()
    del result["records"]
    with pytest.raises(CkanError, match="no records list"):
        parse_page(result)


def test_field_names_are_returned_exactly_as_the_source_spells_them() -> None:
    """Including when the source spelling is wrong.

    The Kalimati 2021+ resource was uploaded with no header row, so CKAN made
    column names out of its first DATA row. A generic client must hand that
    through untouched: repairing it needs knowledge of the dataset, and a
    silent rename would hide the fault from the loader that could verify it.
    """
    result = _result()
    result["fields"] = [
        {"id": "_id", "type": "int"},
        {"id": "Tomato Big(Nepali)", "type": "text"},
        {"id": "2021-01-05 00:00:00", "type": "timestamp"},
    ]
    _, fields, _ = parse_page(result)
    assert fields == ["_id", "Tomato Big(Nepali)", "2021-01-05 00:00:00"]


# --- the authority check -----------------------------------------------------


def _package(**overrides: Any) -> dict[str, Any]:
    package: dict[str, Any] = {
        "name": "kalimati-tarkari-dataset",
        "title": "Kalimati Tarkari Market Dataset",
        "organization": {"title": "Kalimati Fruits and Vegetable Market Development Board"},
        "license_id": "cc-by",
        "license_title": "Creative Commons Attribution",
        "metadata_modified": "2026-06-15T04:39:26.236790",
        "resources": [{"id": "abc", "datastore_active": True, "name": "Prices"}],
    }
    package.update(overrides)
    return package


def test_the_summary_names_the_agency_not_the_aggregator() -> None:
    # Open Data Nepal distributes; the market board is the authority.
    text = summarise(_package())
    assert "Kalimati Fruits and Vegetable Market Development Board" in text
    assert "cc-by" in text


def test_an_open_licence_raises_no_warning() -> None:
    assert "WARNING" not in summarise(_package())


@pytest.mark.parametrize("licence", ["notspecified", "other-closed", None])
def test_a_licence_outside_the_open_set_is_flagged(licence: str | None) -> None:
    # 50 ODN datasets carry `notspecified`; those need founder sign-off, so the
    # check has to be loud at the moment of looking, not a footnote later.
    text = summarise(_package(license_id=licence))
    assert "WARNING" in text


def test_a_dataset_with_no_organisation_still_summarises() -> None:
    # A missing agency is exactly what the check exists to surface — it must
    # not crash before it can report.
    text = summarise(_package(organization=None))
    assert "none named" in text


def test_every_resource_is_listed_with_its_datastore_flag() -> None:
    text = summarise(
        _package(
            resources=[
                {"id": "one", "datastore_active": True, "name": "A"},
                {"id": "two", "datastore_active": False, "name": "B"},
            ]
        )
    )
    assert "datastore_active=True" in text
    assert "datastore_active=False" in text


# --- raw-first archiving -----------------------------------------------------


def test_store_raw_archives_every_page_and_the_package_metadata(tmp_path: Path) -> None:
    """Rule 3: the untouched payload is stored BEFORE anything is parsed.

    Uses a local lake rather than the real one — the raw lake is immutable, so
    a test must never write into it. The point being checked is that nothing
    is dropped: every page's bytes plus the provenance snapshot
    (licence/organisation/modified) must all be inside the archived object.
    """
    from ingestion.common.raw_lake import LocalFilesystemBackend, RawLake
    from ingestion.opendatanepal.ckan_client import DatastoreResult, store_raw

    lake = RawLake(LocalFilesystemBackend(tmp_path))
    result = DatastoreResult(
        resource_id="res-1",
        total=2,
        fields=["_id", "Commodity"],
        rows=[{"_id": 1}, {"_id": 2}],
        pages=[
            ("https://example.test/page0", b'{"page": 0}'),
            ("https://example.test/page1", b'{"page": 1}'),
        ],
    )
    stored = store_raw(lake, "kalimati-tarkari-dataset", result, b'{"license_id": "cc-by"}',
                       "https://example.test/package_show")

    assert stored.payload_path.startswith("opendatanepal/kalimati-tarkari-dataset/res-1/")
    snapshot = json.loads((tmp_path / stored.payload_path).read_text(encoding="utf-8"))
    keys = set(snapshot["members"])
    assert keys == {"page_0000.json", "page_0001.json", "package_show.json"}


def test_store_raw_keeps_each_member_recoverable_byte_for_byte(tmp_path: Path) -> None:
    # One snapshot instead of many objects is a granularity choice, not a
    # weakening: each member must still come back exactly as it arrived.
    import base64

    from ingestion.common.raw_lake import LocalFilesystemBackend, RawLake
    from ingestion.opendatanepal.ckan_client import DatastoreResult, store_raw

    lake = RawLake(LocalFilesystemBackend(tmp_path))
    original = '{"records": [{"Commodity": "गोलभेँडा"}]}'.encode()
    result = DatastoreResult(
        resource_id="res-1", total=1, fields=[], rows=[],
        pages=[("https://example.test/p0", original)],
    )
    stored = store_raw(lake, "ds", result, b"{}", "https://example.test/pkg")

    snapshot = json.loads((tmp_path / stored.payload_path).read_text(encoding="utf-8"))
    page = snapshot["members"]["page_0000.json"]
    assert base64.b64decode(page["payload_b64"]) == original
    assert page["source_url"] == "https://example.test/p0"
