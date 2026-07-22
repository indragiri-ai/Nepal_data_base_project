# Official 2020 political map of Nepal — provenance

**Retrieved:** 2026-07-22
**Purpose:** Replace the portal's pre-2020 boundary files (`web/public/maps/`)
with Nepal's official political map published by the Survey Department in
May 2020 — the map that includes the Limpiyadhura–Lipulekh–Kalapani territory
in Darchula district (Byas Rural Municipality, Sudurpaschim). See
`docs/decisions/0004-official-map.md`.

## Source

- **Originating authority:** Survey Department, Government of Nepal (the
  official national map-maker).
- **Distribution channel:** Open Data Nepal (CKAN), dataset
  *"New political and administrative boundaries Shapefile of Nepal"* —
  <https://opendatanepal.com/dataset/new-political-and-administrative-boundaries-shapefile-of-nepal>
  organization: **Survey Department**; dataset note: *"Downloaded and
  republished from the Survey Department website."*
- **License:** Creative Commons Attribution-ShareAlike (CC-BY-SA, `cc-by-sa`
  in the CKAN metadata). Attribution + share-alike required.
- **Downloaded file:** `raw/local_unit.zip` (ESRI Shapefile set, ~13 MB) via
  the CKAN resource download URL (resource id
  `a1f8ce1e-b2c6-4123-8dc3-13415be95ddc`). Extracted to
  `raw/local_unit_extracted/Local Unit/`.

## What the raw file is

- 777 **local-unit** polygons (the field of interest for us is the boundary
  geometry, not the local-unit count). Attributes: `DISTRICT`, `GaPa_NaPa`
  (local unit), `Province`, `STATE_CODE` (1–7), `Type_GN`.
- **CRS in the .prj:** `NepalDD` on the Everest 1937 (Bangladesh adjustment)
  spheroid — a longlat CRS on the local Nepal datum, **not** WGS84. The offset
  from WGS84 in Nepal is a few hundred metres — invisible at national/district
  zoom, and irrelevant to our choropleth because districts are coloured by
  **P-code attribute join**, not by geometric overlap. We reproject to WGS84
  with mapshaper `-proj wgs84` for consistency with the rest of the portal and
  note the residual datum offset here for honesty.

## How the portal files were derived (reproducible)

All via `npx mapshaper` (same tool/settings as the prior map build):

1. `-proj wgs84` then `-dissolve DISTRICT` → 77 district polygons; and
   `-dissolve Province` → 7 province polygons; and full `-dissolve` → national
   outline (used only to compute area).
2. Property rewrite (Python, full precision) to the portal's existing schema so
   the swap is invisible to the web app:
   - districts → `{DIST_EN, DIST_PCODE, ADM1_PCODE}`
   - provinces → `{ADM1_EN, ADM1_PCODE}`
   73/77 district names auto-matched our existing P-code table by name; the 4
   **split** districts were mapped explicitly and **disambiguated by province
   code** (never guessed):
   | raw `DISTRICT` | `STATE_CODE` | → portal district | P-code |
   |---|---|---|---|
   | `NAWALPARASI_E` | 4 (Gandaki)  | Nawalparasi East | NP0447 |
   | `NAWALPARASI_W` | 5 (Lumbini)  | Nawalparasi West | NP0547 |
   | `RUKUM_E`       | 5 (Lumbini)  | Rukum East       | NP0552 |
   | `RUKUM_W`       | 6 (Karnali)  | Rukum West       | NP0652 |
   Cross-check enforced in code: each district's `ADM1_PCODE` must equal
   `NP0{STATE_CODE}` or the build fails loudly.
3. Simplify `-simplify 4% keep-shapes` (districts) / `8%` (provinces),
   `-clean`, output `precision=0.0001`.

Intermediate outputs kept under `work/` as evidence. The outgoing pre-2020
files are archived (not deleted) under `../pre-2020-archive/`.

## Verification performed (2026-07-22)

- **Darchula (NP0775)** now extends to **max lat 30.4731°N** (was 30.2467°N in
  the pre-2020 file), covering Limpiyadhura (~30.44°N). ✔
- **National area** (spherical estimate) **148,261 km²** vs the official 2020
  figure 147,516 km² → **0.50%** (within the 1% gate). The same estimator gives
  the old file 147,870 km²; the *new − old* delta of +391 km² matches the
  official territory gain of +335 km² (147,516 − 147,181) in direction and
  magnitude — an independent confirmation the Kalapani wedge is really present.
- **All 77 district P-codes** present and unique; **7 provinces** NP01–NP07;
  schema identical to the previous files → `/population` joins all 77 with no
  no-data regions.
- File sizes within budget: districts 307 kB, provinces 232 kB (≤ ~350 kB).
