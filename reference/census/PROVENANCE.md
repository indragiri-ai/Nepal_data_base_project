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
  (with ward counts) — deliberately NOT loaded yet (no dataset needs it; Prime
  Directive 7).
