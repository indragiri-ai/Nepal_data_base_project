# Census 2021 geography reference — provenance

Retrieved 2026-07-19 for the Census 2021 onboarding.

## What was gathered, and from where

1. **NSO census API base**: `https://censusapi.cbs.gov.np/api/v1` — discovered
   as the `baseURL` inside the official results site's JavaScript
   (`censusresults.nsonepal.gov.np`, a Next.js app). Publicly accessible, JSON,
   no auth. Supports `?province=&district=&municipality=` filters.
2. **NSO district list** (`nso_districts_raw.json`): the 77 districts with the
   NSO API's own numeric ids (1–77) and province assignment (1–7), extracted
   verbatim from the site's JS bundles (the list is compiled into the frontend,
   not served by an endpoint). Verification: district count per province is
   14/8/13/11/12/10/9 — exactly the official distribution.
3. **Names** (`en_common.json`, `np_common.json`): the site's own i18n files at
   `/locales/en/common.json` and `/locales/np/common.json` — the source of the
   province names (Koshi, Madhesh, Bagmati, Gandaki, Lumbini, Karnali,
   Sudurpaschim) and ALL Devanagari names (`province_1..7`, plus one key per
   lowercase district label; 77/77 matched).
4. **Boundaries / P-codes**: `mesaugat/geoJSON-Nepal` (GitHub, **MIT license**)
   — `nepal-districts-new.geojson` (77 features) and `nepal-states.geojson`
   (7 features), both carrying official OCHA/Survey-Department P-codes
   (`ADM1_PCODE` NP01–NP07, `DIST_PCODE` NP0101-style, boundary vintage
   2017/11/15, validOn 2019/04/30). **Our geography `code` IS the P-code**, so
   warehouse rows join the map files directly.

## Join: NSO labels ↔ GeoJSON districts

74/77 matched by case/punctuation-insensitive name; 3 spelling variants were
mapped explicitly after checking each was the ONLY unconsumed candidate and sat
in the same province (never guessed):

| NSO label | GeoJSON `DIST_EN` | province |
|---|---|---|
| dhanusa | Dhanusha | 2 (NP02) |
| kavrepalanchok | Kabhrepalanchok | 3 (NP03) |
| makwanpur | Makawanpur | 3 (NP03) |

## Outputs

- `db/seeds/geographies.csv` — +7 provinces +77 districts (level, parent,
  `valid_from=2015-09-20` constitution promulgation, name_en from GeoJSON
  canonical spelling, name_ne from NSO locale).
- `nso_geo_ids.csv` — our code ↔ NSO API ids, used by
  `ingestion/census/pipeline.py` to query the census API per geography.

## Notes

- Province 1 is stored under its current official name (Koshi); Census-2021-era
  publications may say "Province 1" — same entity, same code NP01.
- NSO spells प्रदेश ७ "Sudurpaschim" in English and "सुदुरपश्चिम" in Nepali; we
  keep the source's spellings as-is.
- The municipality (753 local units) list was also seen embedded in the site JS
  (with ward counts) — extracted for P2B.S8 as `nso_munis_raw.json` (see below).

## Municipality level (P2B.S8, added 2026-07-26)

- **`nso_munis_raw.json`** — all **753 local units** with `{district (global NSO
  id 1–77), value (per-district index 1..N), label (name incl. type), wards}`,
  extracted verbatim from the census-results site JS bundle
  (`chunks/8539…js`, the `o=[…]` array), same pattern as the district list.
  **Verification: 753 units and 6,743 wards — both match the official totals.**
- **Municipality data endpoint:** the `/local-level-container/*` family (NOT
  `/population/highlight`, which returns HTTP 500 when `municipality=` is added).
  `/local-level-container/highlight?province=&district=&municipality=` serves
  population + sex per local unit; a wide family of other topics exists
  (household-facility, disability, economic-indicator, migration-indicator,
  literacy-indicator, …) plus `/population/*/ward` for ward level.
- **Known reconciliation quirk (document, don't "fix"):** municipality figures
  do not sum exactly to the district total the district endpoint reports (e.g.
  Taplejung: 9 municipalities sum to 119,450 vs the district's 120,590 — a ~0.9%
  gap). This is inherent to how the census releases municipality vs district
  aggregates; municipality values are shown as-published and labelled, and are
  not forced to reconcile.
- **Boundary join — resolved authoritatively via OCHA COD-AB.** The census NSO
  names romanise ~16 units differently from the *geoportal* boundary layer, so
  rather than a fuzzy geoportal join, they were verified against the official
  **OCHA/UN Nepal Common Operational Dataset – Administrative Boundaries
  (`cod-ab-npl`, HDX)**, whose `npl_admin3` sheet carries official
  **`adm3_pcode`** (e.g. `NP0101301`, extending our district P-codes) + English
  names. **census → COD matched 753/753** (751 exact, 2 obvious variants:
  Melanchi/Melamchi, Manang Ngisyang/Ngisyang). `local_unit_crosswalk.csv` is
  therefore keyed by the official `adm3_pcode` — every local unit has an official
  code, not a minted one. COD-AB (not the geoportal) is the local-unit boundary +
  code source for P2B.S8; the geoportal harvest (`reference/geo/geoportal/`)
  stands as independent verification of the 753 count.
