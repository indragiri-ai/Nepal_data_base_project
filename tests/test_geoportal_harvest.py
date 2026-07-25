"""Tests for NGP.S1 boundary reconciliation. Pure logic — no network, no DB."""

from __future__ import annotations

from typing import Any

from scripts.geoportal_harvest import (
    DISTRICT_ALIASES,
    build_local_unit_mapping,
    reconcile_districts,
    resolve_district,
)

# A tiny stand-in for load_our_districts()'s output: normalised name -> entry.
OURS: dict[str, tuple[str, str, str]] = {
    "taplejung": ("NP0101", "Taplejung", "NP01"),
    "bardiya": ("NP0547", "Bardiya", "NP05"),
    "nawalparasieast": ("NP0436", "Nawalparasi East", "NP04"),
}
# The harvester adds the _E/_W aliases; mirror that here.
for _src, _name in DISTRICT_ALIASES.items():
    key = _name.lower().replace(" ", "")
    if key in OURS:
        OURS[_src.lower().replace("_", "")] = OURS[key]


def _lu(lname: str, dname: str, ltype: str, pname: str, fid: int) -> dict[str, Any]:
    return {
        "properties": {"LNAME": lname, "DNAME": dname, "LTYPE": ltype, "PNAME": pname, "fid_1": fid}
    }


def test_split_district_alias_resolves() -> None:
    # The geoportal's _E suffix must map to our spelled-out "Nawalparasi East".
    assert resolve_district("NAWALPARASI_E", OURS) == ("NP0436", "Nawalparasi East", "NP04")
    assert resolve_district("TAPLEJUNG", OURS) == ("NP0101", "Taplejung", "NP01")


def test_reconcile_reports_unmatched() -> None:
    feats = [
        {"properties": {"DNAME": "TAPLEJUNG"}},
        {"properties": {"DNAME": "NOWHERE"}},
    ]
    matched, unmatched = reconcile_districts(feats, OURS)
    assert matched == 1
    assert unmatched == ["NOWHERE"]


def test_local_unit_mapping_excludes_parks_and_dedupes() -> None:
    feats = [
        _lu("Phaktanglung", "TAPLEJUNG", "Gaunpalika", "Koshi", 1),
        _lu("Bansagadhi", "BARDIYA", "Nagarpalika", "Lumbini", 2),
        _lu("Bansagadhi", "BARDIYA", "Nagarpalika", "Lumbini", 3),  # duplicate feature
        _lu("Shey Phoksundo N.P.", "TAPLEJUNG", "National Park", "Koshi", 4),  # not a unit
    ]
    rows, failures = build_local_unit_mapping(feats, OURS)
    assert failures == []
    names = [r["local_name"] for r in rows]
    assert names.count("Bansagadhi") == 1  # duplicate collapsed
    assert "Shey Phoksundo N.P." not in names  # protected area excluded
    assert len(rows) == 2
    tap = next(r for r in rows if r["local_name"] == "Phaktanglung")
    assert tap["district_code"] == "NP0101"
    assert tap["local_type_en"] == "Rural Municipality"


def test_local_unit_with_unreconciled_district_is_reported() -> None:
    feats = [_lu("Ghost Gaunpalika", "NOWHERE", "Gaunpalika", "Koshi", 9)]
    rows, failures = build_local_unit_mapping(feats, OURS)
    assert rows == []
    assert len(failures) == 1 and "did not reconcile" in failures[0]
