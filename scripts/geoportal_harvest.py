"""NGP.S1 — harvest & reconcile the Survey Department's official admin boundaries.

Downloads three admin-boundary layers from the National Geoportal's public
GeoServer WFS (Government of Nepal, Survey Department), archives each untouched
in the raw lake (raw-first), reconciles them against our own geography codes,
and writes the local-unit ⇄ district mapping that the municipality map (NGP.S2)
and municipality census (P2B.S8) need.

    make geoportal-harvest            # fetch, archive, reconcile, write outputs
    make geoportal-harvest --dry-run  # fetch + reconcile only; archive nothing

Verified facts (recon 2026-07-19/25, see reference/geo/geoportal/PROVENANCE.md):
  - Layer `GIID:base_nepal_local_level_new` serves 777 features: 755 of the four
    municipality LTYPEs + 22 protected areas (parks/reserves — NOT local
    governments). Two municipality features are duplicated (same unit, split
    geometry): 755 − 2 = 753, the official local-unit count.
  - The layer's international boundary is PRE-2020 (the Darchula/Kalapani edge);
    that discrepancy is inherited and noted, not silently shipped.

Nothing here guesses: an unmatched district or an unexpected local-unit count
fails the run with a report (Prime Directive 1).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

import requests

from ingestion.common.io_utf8 import configure_stdout_utf8
from ingestion.common.raw_lake import RawLake

WFS = "https://nationalgeoportal.gov.np/geoserver/ows"
LAYERS = (
    "base_nepal_local_level_new",
    "base_nepal_district_new",
    "base_nepal_province_new",
)
GEOGRAPHIES_CSV = Path("db/seeds/geographies.csv")
OUT_DIR = Path("reference/geo/geoportal")
MAPPING_CSV = OUT_DIR / "local_units_mapping.csv"

# The four LTYPEs that ARE local governments (the other feature types in the
# layer — National Park, Wildlife Reserve, … — are land overlays, not units).
MUNI_TYPES: dict[str, str] = {
    "Gaunpalika": "Rural Municipality",
    "Nagarpalika": "Municipality",
    "Mahanagarpalika": "Metropolitan City",
    "Upamahanagarpalika": "Sub-Metropolitan City",
}

# The geoportal writes the four split districts with an _E/_W suffix; our seed
# spells them out. Explicit, cross-checkable against the feature's province —
# not an inference.
DISTRICT_ALIASES: dict[str, str] = {
    "NAWALPARASI_E": "Nawalparasi East",
    "NAWALPARASI_W": "Nawalparasi West",
    "RUKUM_E": "Rukum East",
    "RUKUM_W": "Rukum West",
}


def _norm(name: str) -> str:
    """Normalise a place name for matching: lowercase, letters only."""
    return re.sub(r"[^a-z]", "", name.lower())


def load_our_districts() -> dict[str, tuple[str, str, str]]:
    """Our 77 districts as {normalised name -> (code, name_en, province_code)},
    including the four _E/_W aliases so the geoportal names resolve."""
    by_norm: dict[str, tuple[str, str, str]] = {}
    with GEOGRAPHIES_CSV.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["level"] == "district":
                entry = (row["code"], row["name_en"], row["parent_code"])
                by_norm[_norm(row["name_en"])] = entry
    for alias_src, our_name in DISTRICT_ALIASES.items():
        key = _norm(our_name)
        if key in by_norm:
            by_norm[_norm(alias_src)] = by_norm[key]
    return by_norm


def resolve_district(
    dname: str, by_norm: dict[str, tuple[str, str, str]]
) -> tuple[str, str, str] | None:
    """Our (code, name_en, province_code) for a geoportal DNAME, or None."""
    return by_norm.get(_norm(dname))


def reconcile_districts(
    features: list[dict[str, Any]], by_norm: dict[str, tuple[str, str, str]]
) -> tuple[int, list[str]]:
    """Match every geoportal district feature to one of ours. Returns
    (matched_count, unmatched_names)."""
    unmatched: list[str] = []
    matched = 0
    for feat in features:
        name = feat["properties"]["DNAME"]
        if resolve_district(name, by_norm) is None:
            unmatched.append(name)
        else:
            matched += 1
    return matched, unmatched


def assemble_local_units(
    features: list[dict[str, Any]], by_norm: dict[str, tuple[str, str, str]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """The 753 official local units, de-duplicated and coded. Keeps only the four
    municipality LTYPEs; merges the split-geometry duplicates into one unit; mints
    a stable `local_code` (district code + 2-digit index within the district,
    sorted by name) — the geoportal serves no municipality code and NSO ids are
    not yet extracted, so this is our internal join key (documented, not claimed
    official). Reports any unit whose district does not reconcile.

    Returns (units sorted by district then name, failures). Each unit carries its
    merged MultiPolygon geometry under `_geometry` for the web-map build."""
    failures: list[str] = []
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    for feat in features:
        p = feat["properties"]
        ltype = p.get("LTYPE", "")
        if ltype not in MUNI_TYPES:
            continue  # protected area, not a local government
        dist = resolve_district(p.get("DNAME", ""), by_norm)
        if dist is None:
            failures.append(f"{p.get('LNAME')} ({p.get('DNAME')}): district did not reconcile")
            continue
        code, dname, prov_code = dist
        key = (code, _norm(p.get("LNAME", "")))
        polys = _as_multipolygon(feat.get("geometry"))
        if key in by_key:
            by_key[key]["_geometry"]["coordinates"].extend(polys)  # merge split parts
            continue
        order.append(key)
        by_key[key] = {
            "local_name": p.get("LNAME", ""),
            "local_type_ne": ltype,
            "local_type_en": MUNI_TYPES[ltype],
            "district_code": code,
            "district_name": dname,
            "province_code": prov_code,
            "province_name": p.get("PNAME", ""),
            "geoportal_fid": str(p.get("fid_1", "")),
            "_geometry": {"type": "MultiPolygon", "coordinates": polys},
        }
    units = [by_key[k] for k in order]
    units.sort(key=lambda u: (u["district_code"], u["local_name"]))
    # local_code: district code + running 2-digit index within the district.
    counter: dict[str, int] = {}
    for u in units:
        counter[u["district_code"]] = counter.get(u["district_code"], 0) + 1
        u["local_code"] = f"{u['district_code']}{counter[u['district_code']]:02d}"
    return units, failures


def _as_multipolygon(geom: dict[str, Any] | None) -> list[Any]:
    """Coordinates of a geometry as a MultiPolygon coordinate list (Polygon is
    wrapped)."""
    if not geom:
        return []
    if geom["type"] == "MultiPolygon":
        return list(geom["coordinates"])
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    return []


# Field order for the mapping CSV (geometry dropped).
_CSV_FIELDS = (
    "local_code",
    "local_name",
    "local_type_ne",
    "local_type_en",
    "district_code",
    "district_name",
    "province_code",
    "province_name",
    "geoportal_fid",
)


def build_local_unit_mapping(
    features: list[dict[str, Any]], by_norm: dict[str, tuple[str, str, str]]
) -> tuple[list[dict[str, str]], list[str]]:
    """The mapping rows (CSV shape — no geometry) for the 753 local units."""
    units, failures = assemble_local_units(features, by_norm)
    rows = [{k: str(u[k]) for k in _CSV_FIELDS} for u in units]
    return rows, failures


def build_local_units_geojson(
    features: list[dict[str, Any]], by_norm: dict[str, tuple[str, str, str]]
) -> tuple[dict[str, Any], list[str]]:
    """Full-resolution 753-feature GeoJSON for the web map (pre-simplification).
    Each feature keys on `local_code` and carries the name/type/district fields."""
    units, failures = assemble_local_units(features, by_norm)
    feats = [
        {
            "type": "Feature",
            "properties": {
                "LUCODE": u["local_code"],
                "LNAME": u["local_name"],
                "LTYPE_EN": u["local_type_en"],
                "DIST_PCODE": u["district_code"],
                "DNAME": u["district_name"],
                "PNAME": u["province_name"],
            },
            "geometry": u["_geometry"],
        }
        for u in units
    ]
    return {"type": "FeatureCollection", "features": feats}, failures


def fetch_layer(name: str, cache_dir: Path | None) -> bytes:
    """Raw GeoJSON bytes for one WFS layer. A cache dir (a prior download) is
    used when present, to avoid re-hammering the geoportal."""
    if cache_dir is not None:
        cached = cache_dir / f"{name}.json"
        if cached.exists():
            print(f"  {name}: using cached {cached} ({cached.stat().st_size:,} bytes)")
            return cached.read_bytes()
    url = (
        f"{WFS}?service=WFS&version=2.0.0&request=GetFeature"
        f"&typeNames=GIID:{name}&outputFormat=application/json"
    )
    print(f"  {name}: fetching from WFS…")
    resp = requests.get(url, timeout=300)
    resp.raise_for_status()
    print(f"  {name}: {len(resp.content):,} bytes")
    return resp.content


def run(argv: list[str] | None = None) -> int:
    configure_stdout_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="fetch + reconcile only; archive nothing"
    )
    parser.add_argument(
        "--cache-dir", type=Path, default=None, help="reuse layer files downloaded here"
    )
    parser.add_argument(
        "--geojson-out",
        type=Path,
        default=None,
        help="also write the full-resolution 753-unit GeoJSON here (for NGP.S2 simplification)",
    )
    args = parser.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    by_norm = load_our_districts()
    lake = None if args.dry_run else RawLake.from_env()

    layers: dict[str, dict[str, Any]] = {}
    raw_refs: dict[str, str] = {}
    print("Harvesting geoportal admin-boundary layers:")
    for name in LAYERS:
        payload = fetch_layer(name, args.cache_dir)
        if lake is not None:
            source_url = (
                f"{WFS}?service=WFS&version=2.0.0&request=GetFeature"
                f"&typeNames=GIID:{name}&outputFormat=application/json"
            )
            stored = lake.store(f"surveydept/geoportal/{name}", payload, source_url)
            raw_refs[name] = stored.payload_path
            print(f"  {name}: archived -> {stored.payload_path}")
        layers[name] = json.loads(payload)

    # --- District reconciliation (77/77 required) ---------------------------
    dist_feats = layers["base_nepal_district_new"]["features"]
    matched, unmatched = reconcile_districts(dist_feats, by_norm)
    print(f"\nDistricts reconciled: {matched}/{len(dist_feats)}")
    if unmatched:
        print("FAILURE: districts did not reconcile (reported, not guessed):")
        for name in unmatched:
            print(f"  - {name}")
        return 1

    # --- Local-unit mapping (753 required) ----------------------------------
    lu_feats = layers["base_nepal_local_level_new"]["features"]
    rows, failures = build_local_unit_mapping(lu_feats, by_norm)
    if failures:
        print("FAILURE: local units did not reconcile:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"Local units mapped: {len(rows)} (official 753)")
    if len(rows) != 753:
        print(f"FAILURE: expected 753 local units, got {len(rows)} — investigate before shipping.")
        return 1

    with MAPPING_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(_CSV_FIELDS))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {MAPPING_CSV} ({len(rows)} rows)")

    if args.geojson_out is not None:
        geojson, _ = build_local_units_geojson(lu_feats, by_norm)
        args.geojson_out.parent.mkdir(parents=True, exist_ok=True)
        args.geojson_out.write_text(
            json.dumps(geojson, ensure_ascii=False), encoding="utf-8"
        )
        n_feats = len(geojson["features"])
        print(f"Wrote full-resolution GeoJSON -> {args.geojson_out} ({n_feats} features)")

    from collections import Counter

    by_type = Counter(r["local_type_en"] for r in rows)
    print("  by type:", dict(by_type))
    print("Done." if args.dry_run else f"Done. Raw archived: {list(raw_refs.values())}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
