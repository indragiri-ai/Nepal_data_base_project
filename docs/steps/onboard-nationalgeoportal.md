# Onboarding: National Geoportal (Survey Department) — Step File

**Version 1.0 — 2026-07-19. Recon by Fable 5; implementation by any capable
model. House rules apply. This is a GIS/boundary source, not a statistics
source — it feeds the MAP layer of the portal.**

---

## Verified facts (2026-07-19)

- `nationalgeoportal.gov.np` (SPA) sits on a **GeoServer** at
  `https://nationalgeoportal.gov.np/geoserver/ows` — standard **WFS** works
  unauthenticated: `?service=WFS&version=2.0.0&request=GetCapabilities`;
  features as GeoJSON via
  `&request=GetFeature&typeNames=<layer>&outputFormat=application/json`.
- **82 layers.** The relevant ones:
  - Admin boundaries: `GIID:base_nepal_new` (national), `GIID:base_nepal_district_new`,
    `GIID:base_nepal_province_new`, **`GIID:base_nepal_local_level_new`**
    (753 local units — official!), `geonode:wards`, plus `_old` variants
    (pre-2015 structure: old districts, VDCs).
  - Other assets: `geonode:health_facilities`, `GIID:base_river`,
    `GIID:base_peak`, `GIID:base_pass`, roads (`trans_ln`), settlements,
    land cover, contours.
- **CRITICAL NEGATIVE FINDING — tested, not assumed:** none of the national
  layers (`base_nepal_new`, `App_nepal`, `geonode:nepal`) contain the
  Kalapani-triangle test point (80.75E, 30.30N) — i.e. **the geoportal's WFS
  still serves the PRE-2020 international boundary**. "new"/"old" in layer
  names = the 2015 federal restructure, NOT the 2020 political map. (Control
  point 84.0E/28.0N verified inside; ray-casting point-in-polygon; national
  outline is 1 feature, ~1.7 MB.) Also confirmed the same day: **our own
  `web/public/maps/nepal-districts.json` Darchula tops out at 30.247N — 
  pre-2020 as suspected.**
- Consequence for **P2B.S1** (official-map step): the geoportal is CHECKED
  and ruled out as the 2020-boundary source. Remaining channels: OCHA/HDX
  COD-AB updates endorsed after May 2020, opendatanepal/OKN, post-2020
  GitHub digitizations (each must pass the S1 verification tests), or a
  direct request to the Survey Department. If none verify → the S1 fallback
  (visible disclaimer) stands. **Do not re-probe the geoportal for this.**
- Authority & license: this IS the Survey Department / Government of Nepal's
  own publication channel — top-tier authority for the boundaries it DOES
  serve (2015-structure admin layers). No explicit license text found on the
  WFS; record as "Government of Nepal, Survey Department — official
  geoportal, open WFS; license statement not published" and attribute
  clearly. Be polite: sequential requests, delays, cache in the raw lake.

## What we take, in order of value

| # | Layer(s) | Feeds |
|---|---|---|
| T1 | `base_nepal_local_level_new` (753 local units) | **P2B.S8's municipality map** — replaces the MIT-mirror municipalities file with the OFFICIAL one |
| T2 | `base_nepal_district_new` + `base_nepal_province_new` | Cross-check of our current district/province geometries + P-code/name reconciliation |
| T3 | `geonode:health_facilities` | A health-facilities layer for the Health sector (points → per-district counts) |
| T4 | `geonode:wards` | Parked until ward-level data exists (P2B facts: 6,743 wards) — inventory only |

---

### NGP.S1 — Harvest + archive the admin-boundary layers

**GOAL:** The official 2015-structure boundary set (local units, districts,
provinces) archived raw and reconciled against our geography codes.

**ACTIONS:** Instruct the implementing model:
> "Via WFS GetFeature (GeoJSON), download `base_nepal_local_level_new`,
> `base_nepal_district_new`, `base_nepal_province_new`. These may be large
> (the national outline alone is 1.7 MB; local units likely tens of MB) — 
> stream to disk, then store each in the raw lake under
> `surveydept/geoportal/<layer>/` with the request URL, plus a
> `reference/geo/geoportal/PROVENANCE.md` (layer list, retrieval date, the
> pre-2020-boundary finding restated). FIRST inspect one feature's
> properties per layer (print them): find the fields carrying district/
> local-unit names and codes. Reconcile: (a) district layer joins our 77
> P-codes — expect name-based joining with the census alias rules
> (dhanusa/kavrepalanchok/makwanpur precedent); every district must match or
> the run fails with a report; (b) local-unit layer: match count vs official
> 753 and against `reference/census/` municipality extraction (NSO ids) —
> produce the local-unit ⇄ NSO-id ⇄ (any official code present) mapping CSV
> that P2B.S8 needs. Unmatched units → listed, never guessed."

**VERIFICATION:** 3 layers raw-archived; property inventory committed;
77/77 districts reconciled; local-unit count vs 753 reported with the
mapping CSV; lint/test green.

**COMMIT:** `NGP.S1: official admin boundaries harvested + reconciled (753/77/7)`

---

### NGP.S2 — Official municipality map file for the web

**GOAL:** `web/public/maps/nepal-local-units.json` — simplified, P2B.S8-ready.

**ACTIONS:**
> "From the raw local-units GeoJSON: simplify with mapshaper (`keep-shapes`,
> precision 0.0001; target ≤ ~600 kB — tune the percentage; report final
> size), keep only the name/code fields identified in NGP.S1, write to
> web/public/maps/. Verify feature count (753) and that a sample of 10 units
> sits inside the right district polygon (point-in-polygon of a vertex
> against our district file). NOTE in the file's provenance comment AND in
> P2B.S8: the Darchula-area edge is pre-2020 (inherited from this source);
> when P2B.S1 lands a verified 2020 boundary, the local-unit layer inherits
> the discrepancy note until an updated official layer exists."

**VERIFICATION:** 753 features; ≤ ~600 kB; 10/10 sample containment; loads in
the existing ChoroplethMap without code changes (registerMap accepts it).

**COMMIT:** `NGP.S2: official 753-local-unit web map (P2B.S8 unblocked)`

---

### NGP.S3 — Health facilities layer (optional, founder-pleasing)

**GOAL:** Health-facility density on the map — the Health sector's first
geographic layer.

**ACTIONS:**
> "Harvest `geonode:health_facilities` (points; archive raw; inspect
> properties — type/name/location fields). Aggregate to per-district COUNTS
> (point-in-polygon against our districts), load as indicator
> `HEALTH_FACILITIES_COUNT` (unit COUNT, breakdowns={\"facility_type\": …} if
> the type field is clean — else no breakdown, noted), geography = district,
> period = a single 'as published' year (read any date field in the layer
> metadata; if none, use the retrieval year with definition text 'as served
> by the geoportal, retrieval 2026' — honest, dated). Direct load is
> acceptable (machine-served official layer) but run the quality gate
> (counts positive, total plausible vs ~5,000–8,000 known facilities —
> verify magnitude from the layer itself first). Choropleth via the existing
> /v1/data/geo. Spot-check: one district's count re-derived independently."

**COMMIT:** `NGP.S3: health facilities per district — official layer, mapped`

---

## Also updated by this recon (do not redo)

- **P2B.S1** carries a note (added 2026-07-19): geoportal channel checked —
  pre-2020 boundaries; skip straight to the other channels.
- **P2B.S8** gains its official boundary source (NGP.S2 output) instead of
  the MIT-mirror municipalities file.

Order: NGP.S1 → S2 (unblocks P2B.S8) → S3 optional. ~3 sessions.
