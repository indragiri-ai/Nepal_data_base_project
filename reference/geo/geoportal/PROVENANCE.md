# National Geoportal admin boundaries — provenance (NGP.S1)

**Source:** Government of Nepal, **Survey Department** — official National
Geoportal (`nationalgeoportal.gov.np`), a GeoServer exposing an open,
unauthenticated **WFS 2.0** at `https://nationalgeoportal.gov.np/geoserver/ows`.
**Retrieved:** 2026-07-25 (recon 2026-07-19). **License:** no explicit statement
published on the WFS — recorded as *"Government of Nepal, Survey Department —
official geoportal, open WFS; license statement not published"* and attributed
clearly wherever used.

Harvested by `scripts/geoportal_harvest.py` (`make geoportal-harvest`), which
archives each layer untouched in the raw lake before any parsing (raw-first),
then reconciles against our geography codes. An unmatched district or an
unexpected local-unit count **fails the run with a report** — never guessed.

## Layers taken (GeoJSON via WFS GetFeature)

| Layer (`GIID:`) | Features | Raw-lake prefix |
|---|---|---|
| `base_nepal_local_level_new` | 777 → **753** local units (see below) | `surveydept/geoportal/base_nepal_local_level_new/` |
| `base_nepal_district_new` | 77 | `surveydept/geoportal/base_nepal_district_new/` |
| `base_nepal_province_new` | 7 | `surveydept/geoportal/base_nepal_province_new/` |

## Property inventory (one feature per layer, verbatim field names)

- **local units** — `fid_1`, `PCODE` (province number, *not* a municipality
  code), `DNAME` (district, UPPERCASE), `LNAME` (local-unit name), `LTYPE`
  (Gaunpalika / Nagarpalika / Mahanagarpalika / Upamahanagarpalika / protected
  areas), `PNAME` (province). Geometry: MultiPolygon.
- **districts** — `fid_1`, `DNAME`, `PCODE`, `PNAME`.
- **provinces** — `fid_1`, `PCODE`, `PNAME_N` (Devanagari), `PNAME_E` (English).

## The 777 → 753 reconciliation (tested, not assumed)

The local-level layer serves **777 features**:

- **755** of the four local-government types — Gaunpalika 461, Nagarpalika 277,
  Mahanagarpalika 6, Upamahanagarpalika 11.
- **22 protected areas** (National Park 11, Wildlife Reserve 6, Hunting Reserve
  3, Watershed & Wildlife Reserve 1, Development Area 1) — land overlays, **not
  local governments**; excluded.
- The 755 include **2 duplicated features** (same unit, split geometry):
  *Bansagadhi* (Bardiya) and *Binayee Tribeni* (Nawalparasi East). Collapsed by
  (district, name).

755 − 2 = **753**, the official local-unit count. Final by type after dedup:
Rural Municipality 460, Municipality 276, Metropolitan City 6,
Sub-Metropolitan City 11.

## District reconciliation

77/77 districts match our seed by normalised name. The four split districts are
written by the geoportal with an `_E`/`_W` suffix; mapped explicitly (and
cross-checked against the feature's province) to our spelled-out names:
`NAWALPARASI_E → Nawalparasi East`, `NAWALPARASI_W → Nawalparasi West`,
`RUKUM_E → Rukum East`, `RUKUM_W → Rukum West`.

## Output

`local_units_mapping.csv` — one row per official local unit: `local_name`,
`local_type_ne`, `local_type_en`, `district_code` (our P-code), `district_name`,
`province_code`, `province_name`, `geoportal_fid`.

**No official municipality code is available:** the layer's only code (`PCODE`)
is the province number, and NSO municipality ids are **not yet extracted**
(`reference/census/nso_geo_ids.csv` is district-level only). P2B.S8 will join
municipality census data to this mapping **by (district, name)**, or first
gather the municipality NSO-id list from the census API.

## Web map (NGP.S2) — `web/public/maps/nepal-local-units.json`

Built from the raw local-unit layer, reproducibly:

1. `make geoportal-harvest ... --geojson-out <full>.geojson` writes the
   full-resolution 753-feature GeoJSON (4 municipality LTYPEs, duplicates merged,
   each feature keyed on `LUCODE` with `LNAME`/`LTYPE_EN`/`DIST_PCODE`/`DNAME`/`PNAME`).
2. `npx mapshaper <full>.geojson -simplify 1.5% keep-shapes -o precision=0.0001
   format=geojson web/public/maps/nepal-local-units.json` (→ 753 features, ~590 kB).
3. A top-level `_provenance` string is injected (echarts `registerMap` ignores it).

**Verified:** 753 features; ~592 kB (≤ ~600 kB target); 10/10 sampled units'
representative point falls inside their assigned district polygon
(`nepal-districts.json`, by `DIST_PCODE`); structure matches the district/province
map files, so `registerMap` accepts it unchanged (P2B.S8 wires the render). Key
property for joins: **`LUCODE`** (our internal code — see the local-code note above).

## ⚠ Boundary vintage — PRE-2020

Verified 2026-07-19: none of the geoportal's national layers contain the
Kalapani/Limpiyadhura triangle — the WFS still serves the **pre-2020**
international boundary (the "new"/"old" in layer names is the 2015 federal
restructure, not the 2020 political map). The local-unit layer inherits this:
the **Darchula-area edge is pre-2020**. This is carried with a visible note (as
in P2B.S1) until a verified 2020 official layer exists. Do not re-probe the
geoportal for the 2020 boundary — that channel is ruled out.
