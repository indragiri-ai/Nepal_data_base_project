# Onboarding: Open Data Nepal (opendatanepal.com) — Step File

**Version 1.0 — 2026-07-19. Recon by Fable 5 (all facts below verified live
that day); implementation by any capable model. Follows the house step format;
the P2B standing rules apply (gates green, raw-first, idempotent,
report-never-guess, log every session).**

---

## What this source IS (read before building)

**Open Data Nepal is an AGGREGATOR, not an origin.** It is a CKAN portal (run
by the Open Knowledge Nepal community) hosting datasets **re-published from
government agencies** — the data's *authority* comes from the originating
agency (Kalimati Market Board, Dept. of Health Services, CBS, …), while ODN is
the *distribution channel*. This changes how we record provenance:

- **`sources` row = the originating agency** (e.g. "Kalimati Fruits and
  Vegetable Market Development Board", type `ministry` or the closest CHECK
  value — inspect `sources.type` CHECK in `db/migrations/0001` and pick;
  extend the CHECK via migration ONLY if truly nothing fits).
- **`datasets` row = the ODN dataset** (access_method=`api`), with
  `documentation_url` = the ODN dataset page AND the dataset's `notes` field
  recording the original agency URL (e.g. kalimatimarket.gov.np).
- **Vintage honesty:** many ODN datasets are historical snapshots (tourism to
  2014, health FY 2073/74). That's fine — historical series don't go stale —
  but the indicator `definition_en` MUST state the coverage window, and the
  frontend must never present a closed historical series as "current".
- **Per-dataset authority check (mandatory):** before onboarding any dataset,
  confirm the ODN metadata names a real agency + original URL, and the license
  is open (`cc-by` / `cc-by-sa` / `cc-zero` / `odc-by`). `notspecified` (50
  datasets) → do NOT onboard without founder sign-off, listed in a report.

## Verified facts bank (2026-07-19 — cite, don't re-derive)

- Frontend `opendatanepal.com` (Next.js) → **CKAN API base:
  `https://api.opendatanepal.com/api/3/action`** (found as the hardcoded base
  in the site's JS). Standard CKAN: `package_search`, `package_show`,
  `organization_list`, `datastore_search`. No auth for reads.
- **382 datasets · 25 organizations.** Top publishers: CBS (91), Dept. of
  Health Services (39), Min. of Agricultural Development (12), Dept. of
  Hydrology & Meteorology (9), Dept. of Roads (7), Min. of Culture, Tourism &
  Civil Aviation (7). Licenses: cc-by 287, cc-by-sa 39, notspecified 50,
  others few. Formats: CSV 377 of 382.
- **CKAN Datastore is ACTIVE on most resources** — `datastore_search` returns
  clean JSON rows (paged via `limit`/`offset`; `total` in result). This is the
  ingestion channel: NO CSV-download parsing needed where
  `resource.datastore_active == true`.
- Datasets actively maintained: multiple `metadata_modified` = 2026-06-15.
- **Verified sample record** (Kalimati, resource
  `b791b8cd-7ed4-445c-ad8d-69bf58a2c8d4`, row 1): `Commodity="Tomato
  Big(Nepali)", Date="2013-06-16", Unit="Kg", Minimum=35.0, Maximum=40.0,
  Average=37.5`. Fields: `SN, Commodity, Date (YYYY-MM-DD), Unit, Minimum,
  Maximum, Average`. Two resources cover Jun-2013→May-2021 and May-2021→
  onward.
- Org slugs for `fq=organization:<slug>`: `kalimati-fruits-and-vegetable-
  market-development-board`, `ministry-of-culture-tourism-and-civil-aviation`,
  `department-of-hydrology-and-meteorology`, `department-of-health-services`,
  `central-bureau-of-statistics`, `department-of-foreign-employment`, …
  (full list via `organization_list`).

## What we take first (curated — value per effort, founder-aligned)

| # | Dataset | Sector | Why |
|---|---|---|---|
| T1 | **Kalimati daily fruit & vegetable prices (2013→present)** | Agriculture & Environment | The flagship: daily, decade-long, touches everyday life ("what did tomatoes cost?"), maintained, cc-by, datastore-active. Nothing like it on our portal. |
| T2 | **Monthly tourist arrivals 1992–2014** (+ annual 2000–2014) | Economy | Long historical series for the tourism story; label the window; a later source (Nepal Tourism Statistics) can extend it to the present. |
| T3 | **Climate: monthly normals 1980–2010 (20 stations) + observed trends 1971–2014 + monsoon onset/withdrawal** | Agriculture & Environment | Seeds the climate corner of the Environment sector with real DHM data. |
| T4 | **Health service statistics by province (FY 2073/74 era)** | Health | First provincial health data; exercises BS fiscal-year periods on a non-NRB source. |

Everything else (CBS's 91, roads, election, foreign employment…) is cataloged
for later — S5 below produces the triage report.

---

### ODN.S1 — CKAN client + raw-first acquisition (the reusable core)

**GOAL:** A generic, reusable CKAN ingestion helper — because ODN is CKAN,
and so are many other government portals; this helper is the template
(P2B.S11) paying off.

**ACTIONS:** Instruct the implementing model:
> "Create `ingestion/opendatanepal/ckan_client.py`: (a)
> `fetch_package(dataset_id)` → `package_show` JSON; (b)
> `fetch_datastore_rows(resource_id)` → ALL rows via `datastore_search`
> paging (limit 1000, follow offset until `total`), returning rows + the raw
> page payloads; (c) `store_raw(lake, dataset, resource_id, pages)` → each
> page to the raw lake under `opendatanepal/<dataset-slug>/<resource-id>/`
> BEFORE parsing, plus the `package_show` metadata JSON alongside (that's the
> provenance snapshot: license, org, notes, modified date). Timeout 60s,
> one retry, fail loudly on `success != true`. Offline tests with a captured
> fixture page. UTF-8 stdout everywhere (house rule — data has Devanagari)."

**VERIFICATION:** fixture test green; a live pull of the Kalimati resource's
first page stores raw + parses `total` correctly; `make lint`/`make test`
green.

**COMMIT:** `ODN.S1: reusable CKAN client — datastore paging, raw-first`

---

### ODN.S2 — T1: Kalimati daily prices end to end (the flagship)

**GOAL:** Daily wholesale prices for a curated commodity basket, 2013→present,
in the warehouse and on the Environment/Agriculture sector page.

**Modeling decisions (made — do not revisit):**
- **Daily periods:** inspect `time_periods.period_type` CHECK (migration
  0002). If `'day'` is absent, add it via a new migration (CHECK extension
  only). Create day periods ON DEMAND for dates present in the data
  (gregorian_start=gregorian_end=date, label YYYY-MM-DD, sort_key per
  decision 0002 date scheme). Do NOT pre-seed 5,000 days.
- **Commodity basket:** to respect free-tier headroom, load a curated TOP-25
  basket first (rank commodities by row-presence across the full series;
  take the top 25; list them in the seed CSV — reviewable data). The full
  list is a later extension; note it.
- **Shape:** one indicator per commodity is WRONG (25 indicators × nothing
  shared). Instead ONE indicator `KALIMATI_PRICE_AVG` (unit: new
  `NPR_PER_KG`) with `breakdowns={"commodity": <name>}`; Min/Max stored as
  `KALIMATI_PRICE_MIN`/`_MAX` only for the basket (same breakdown key). Rows
  with `Unit != "Kg"` (e.g. per piece, per dozen): keep only Kg rows in v1,
  count and report the rest — never silently convert units.
- **Status:** `final` (published market records).
- Expect ≈ 25 commodities × ~4,800 days × 3 stats ≈ **~250–350k rows**. Batch
  inserts (existing executemany pattern); after load, report
  `pg_database_size` headroom. If projected > 200 MB, STOP and consult the
  founder (options: avg-only, or top-10 basket).

**ACTIONS:** Instruct:
> "Find the dataset via `package_search?q=kalimati`; take BOTH resources
> (2013–2021 and 2021→). Acquire raw via ODN.S1. Parser: field contract is
> the facts-bank sample (SN/Commodity/Date/Unit/Minimum/Maximum/Average);
> unknown fields or unparseable dates fail loudly. Normalize commodity names
> ONLY for whitespace/case; spelling variants stay as published (they're the
> breakdown key; a variants report is produced for later curation). Seeds:
> source row (Kalimati Fruits and Vegetable Market Development Board, url
> kalimatimarket.gov.np), dataset row (ODN access), unit NPR_PER_KG,
> indicators registry + CSV locked by test (census pattern). Quality gate
> bands: price in (0, 10000] NPR/kg (generous; catches unit errors), Min ≤
> Avg ≤ Max as a hard rule per row. This is re-published human-uploaded data:
> route through the NRB-style staging+review gate (rule 3) — extract to
> staging, spot-check, founder-visible approve step, promote. Idempotent at
> every stage. Spot-checks: (1) the facts-bank tomato row EXACTLY; (2) one
> recent date verified against kalimatimarket.gov.np's own daily price page
> (independent channel). Frontend: 'Market prices' panel on the Environment
> sector page — commodity picker (basket), daily line with a monthly-average
> toggle (client-side downsample for readability), CSV download, provenance
> naming BOTH the market board (source) and Open Data Nepal (distributor)."

**VERIFICATION:** both spot-checks exact; Min≤Avg≤Max holds warehouse-wide
(query proof); re-run idempotent; DB headroom reported; chart renders daily +
monthly views; lint/test/build green.

**IF IT GOES WRONG:** The two resources overlap in May 2021 → the change-aware
loader makes duplicates impossible per (indicator, period, breakdowns); verify
the overlap rows agree — if they conflict, prefer the newer resource and log
the count. Datastore times out on deep offsets → reduce page size to 500.

**COMMIT:** `ODN.S2: Kalimati daily prices — basket of 25, staged+reviewed, charted`

---

### ODN.S3 — T2 + T3: tourism (historical) and climate

**GOAL:** Monthly tourist arrivals 1992–2014 into Economy; DHM climate
normals/trends/monsoon dates into Environment.

**ACTIONS:** Instruct:
> "Tourism: `Monthly Tourist Arrivals in Nepal (1992–2014)` (+ the annual
> 2000–2014 set as cross-check, not as separate observations). Indicator
> TOURIST_ARRIVALS (COUNT), monthly Gregorian periods (period_type month —
> check CHECK, extend if absent, same rule as days), definition states the
> window and that the series is CLOSED at 2014 pending a successor source.
> Cross-check: 12-month sums vs the annual dataset — mismatches reported,
> not reconciled silently. Climate: normals 1980–2010 per station → this is
> STATION-level, not geography-level — model stations as breakdowns
> ({\"station\": name}) on national-scope indicators (CLIMATE_NORMAL_TEMP_*,
> CLIMATE_NORMAL_PRECIP, units °C / MM — new units), periods = the
> climatological month (use the representative month period with the window
> in the definition; do NOT invent per-year rows for a 1980–2010 normal).
> Monsoon onset/withdrawal dates: two indicators, value = day-of-year, with
> the date in a footnote — or SKIP with a note if the shape resists honest
> modeling (report back; don't force). Same staging+review gate; same
> provenance duality (agency source, ODN distributor); sector wiring:
> tourism → Economy page list, climate → Environment."

**VERIFICATION:** tourism 12-month sums cross-check reported; a known year
matches an external published figure (e.g. verify one year against the
Ministry's published tourism statistics PDF); climate spot-check 2 station
normals against the raw rows; idempotent; gates green.

**COMMIT:** `ODN.S3: tourism 1992–2014 + DHM climate — historical, labeled, cross-checked`

---

### ODN.S4 — T4: provincial health statistics

**GOAL:** First health data below national level, on BS fiscal-year periods.

**ACTIONS:** Instruct:
> "From `department-of-health-services` (39 datasets) select the FY 2073/74
> 'Health Service Statistics' + 'Immunization Coverage by Antigen' +
> 'FP current users by Province' sets. Map province names → our NP01–NP07 via
> name matching against `geographies` (the 2017-era files may use 'Province
> 1'-style names — map number→P-code, NEVER fuzzy-match beyond that; unmatched
> fails loudly). Periods: BS fiscal years via the existing `seed-periods-ne`
> machinery (FY 2073/74 exists in bs_calendar range). Indicators registry
> (HEALTH_* codes, PCT/COUNT units, definitions stating the FY window),
> staging+review, provenance duality. Frontend: rows appear in the Health
> sector list; no new dashboard needed yet."

**VERIFICATION:** every province resolved to a P-code (0 unmatched); one value
re-verified against the DoHS annual report PDF (independent channel);
idempotent; gates green.

**COMMIT:** `ODN.S4: provincial health statistics FY 2073/74 (BS fiscal periods)`

---

### ODN.S5 — Catalog triage report (no loading)

**GOAL:** A founder-readable inventory of the remaining ~370 datasets so the
next picks are choices, not archaeology.

**ACTIONS:** Instruct:
> "Sweep `package_search` over all 382 datasets; produce
> `reference/opendatanepal/catalog_triage.csv` + a short memo: per dataset —
> org, title, license, modified, datastore_active, coverage window (from
> title/notes where stated), our-sector guess, and a 0–3 value score
> (3 = unique + maintained + open license + fits a sector gap). Flag the 50
> `notspecified` licenses in their own section. No data loading in this step."

**COMMIT:** `ODN.S5: Open Data Nepal catalog triage (382 datasets scored)`

---

## Order & effort

ODN.S1 → S2 (flagship) → S3 → S4 → S5. Roughly 5–7 sessions. S1+S2 first —
Kalimati alone justifies the source. After S5, the founder picks the next
batch from the triage memo. Scheduled refresh: add the Kalimati pull to the
P2B.S2 workflow (weekly; the source updates continuously) — the other three
targets are closed/historical and need no schedule.
