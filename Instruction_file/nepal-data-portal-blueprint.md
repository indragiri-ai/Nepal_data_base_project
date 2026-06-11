# Nepal Data Portal — Architecture Blueprint

**Version 1.0 — June 2026**
**Status: Founding document. Update the version number whenever a decision changes.**

> How to use this document: This is the project's permanent memory. Upload it at the start of every working session with Claude (or keep it in a Claude Project's knowledge) so work always continues from the same foundations. When a decision in here changes, update the document — never let it drift out of date.

---

## 1. Vision

A single, trustworthy, free portal where anyone — researchers, journalists, students, policymakers, businesses — can find data about Nepal in one place, in consistent formats, with visualizations, downloads, and a public API.

**What makes it different from existing options:**
- Not a file dump. Every dataset is *harmonized* into one common structure, so a census figure, an NRB statistic, and a World Bank indicator can be charted together on the same timeline.
- Every number carries its source, license, definition, and revision history.
- Bilingual (English and Nepali) from day one.
- Works across Nepal's calendar systems and the 2015 federal restructuring of boundaries — the two problems that quietly break most Nepali datasets.

**Initial data sources (in order of integration):**
1. World Bank Open Data API (Nepal indicators)
2. IMF data (SDMX API)
3. ILOSTAT (labor statistics)
4. NRB — Nepal Rastra Bank (monetary, banking, external sector; Excel/PDF publications)
5. NSO/CBS — censuses 2011 & 2021, surveys (NLSS, labor force, agriculture)
6. Ministry and departmental publications (health, education, budget; mostly PDF)

---

## 2. Core principles (non-negotiable)

1. **One universal data model.** All statistical data is stored as observations of *indicator × geography × time period (× optional breakdowns) = value*. New datasets are mapped into this shape; the portal never grows per-dataset special cases.
2. **Raw data is immutable.** Every source file (Excel, PDF, API response) is stored exactly as received, forever, with a timestamp and source URL. Nothing is ever cleaned "in place."
3. **All transformation is code.** Cleaning and harmonization happen through saved, repeatable scripts — never manual edits to data. Any published number can be regenerated from raw files.
4. **Metadata first.** A number without source, definition, unit, and license attached does not enter the warehouse.
5. **Revisions are versioned.** When a source revises a figure, both the old and new values are kept, each tagged with its release date ("vintage"). The portal shows the latest by default but can reconstruct what was known at any time.
6. **Boring technology.** PostgreSQL, Python, standard web frameworks. Chosen for 10-year durability, free/open-source licensing, and the largest possible pool of help.
7. **Bilingual by design.** All human-facing names (indicators, places, categories) have English and Nepali fields in the schema itself.
8. **Small verified steps.** Each build phase produces something inspectable and working before the next begins.

---

## 3. Architecture overview (the six layers)

```
SOURCES → INGESTION → RAW LAKE → TRANSFORMATION → WAREHOUSE + CATALOG → API → PORTAL
```

| Layer | Job | Technology |
|---|---|---|
| Ingestion | Pull data from APIs, scrape/download files, accept manual uploads | Python scripts |
| Raw data lake | Store original files immutably | Object storage (Supabase Storage / S3-compatible) |
| Transformation | Clean, convert calendars, map geographies, standardize units | Python + dbt (later) |
| Warehouse | The harmonized database all queries run against | PostgreSQL |
| Metadata catalog | Sources, licenses, definitions, lineage | Tables inside PostgreSQL |
| API | Serve data to the website and the public | FastAPI (Python), heavy caching |
| Portal | Search, charts, maps, downloads | Next.js + ECharts, GeoJSON maps |

**Orchestration** (scheduling pipelines to run automatically) is added in Phase 4 with Dagster. Early phases run scripts manually — correctness before automation.

---

## 4. The data model (the heart of the project)

### 4.1 The universal shape

Every statistic, from any source, becomes one row in an `observations` table:

> *"Literacy rate (indicator) in Bagmati Province (geography) for census year 2021 (time period), female (breakdown) = 81.4 % (value, unit), per NSO Census 2021 (source/release), final (status)."*

### 4.2 Core tables

**sources** — one row per publishing organization.
- id, name_en, name_ne, type (international / central bank / statistics office / ministry), url, default_license, notes

**datasets** — a publication or API from a source (e.g. "NRB Quarterly Economic Bulletin", "World Bank WDI").
- id, source_id, name_en, name_ne, license, update_frequency, access_method (api / file / scrape / manual), documentation_url

**releases** — one row each time a dataset is published/updated. This is what enables revision tracking.
- id, dataset_id, release_date, period_covered, raw_file_refs, notes

**indicators** — the master list of measurable things.
- id, code (stable, human-readable, e.g. `POP_TOTAL`, `CPI_YOY`, `LIT_RATE`), name_en, name_ne, definition_en, definition_ne, unit_id, topic (population / economy / labor / health / education / agriculture / environment / governance), source_concept (the source's own code, e.g. World Bank `SP.POP.TOTL`), preferred_source_id

**units** — `%`, `NPR million`, `persons`, `per 1,000 live births`, etc., with conversion notes.

**geographies** — every place, at every administrative level, with validity periods.
- id, code, name_en, name_ne, level (country / province / district / local_unit / old_region / old_district), parent_id, valid_from, valid_to, geometry_ref (link to boundary file for maps)
- Both the pre-2015 structure (5 development regions, 75 districts) and the current structure (7 provinces, 77 districts, 753 local units) exist as rows, distinguished by level and validity dates.

**geography_crosswalk** — maps old units to new ones with an allocation share, so pre-2015 data can be approximately re-expressed in current boundaries (and flagged as estimated when it is).
- old_geo_id, new_geo_id, share, method, notes

**time_periods** — the calendar bridge (see §5.1).
- id, period_type (year / fiscal_year / quarter / month / census_round), gregorian_start, gregorian_end, bs_label (e.g. "2080/81"), gregorian_label (e.g. "FY 2023/24"), sort_key

**observations** — the big fact table.
- id, indicator_id, geography_id, time_period_id, value (numeric), unit_id, breakdowns (JSONB: e.g. `{"sex":"female","age":"15+"}`), dataset_id, release_id, status (provisional / revised / final / estimated), is_latest (boolean, maintained automatically), footnote
- Unique constraint on (indicator, geography, time_period, breakdowns, release) — the same number from a newer release becomes a new row, and `is_latest` moves to it.

**ingestion_log** — every pipeline run: what ran, when, how many rows, success/failure, link to raw files. The audit trail.

### 4.3 Design rules

- Indicator `code`s are permanent. Renaming the display name is fine; changing a code is not.
- One indicator can have data from multiple sources (e.g. GDP from both NSO and World Bank). They coexist as separate observations tagged by dataset; the portal can show them side by side. A `preferred_source_id` decides the default display.
- The `breakdowns` JSONB column keeps the model flexible without schema changes — but every breakdown key used must be documented in the catalog.
- Nothing is deleted. Wrong data is superseded by a new release or flagged, never erased.

---

## 5. Nepal-specific harmonization rules

### 5.1 Calendars and fiscal years

- Nepali sources use **Bikram Sambat (BS)**; the fiscal year runs **Shrawan to Ashadh (≈ mid-July to mid-July)**. International sources use Gregorian calendar years.
- Rule: the `time_periods` table stores every period **once**, with its exact Gregorian start/end dates plus its BS and fiscal labels. Data is attached to periods, never to bare year numbers.
- Consequence: "2080/81 BS", "FY 2023/24", and "Q3 2024" can all be plotted on one true time axis without ambiguity.
- A BS↔AD conversion table (day-level) is loaded as reference data; conversions are never done by formula (BS month lengths are irregular).

### 5.2 Geography and the 2015 restructuring

- The 2015 constitution replaced 5 development regions / 75 districts with 7 provinces / 753 local units (districts became 77).
- Census 2011 and older data use old boundaries; Census 2021 and current administrative data use new ones.
- Rule: data is always stored against the boundaries it was published in. Comparison across the break uses the `geography_crosswalk`, and any crosswalked figure is displayed with an "estimated via boundary mapping" flag.
- Place-name spellings vary wildly across sources (romanization of Nepali). A `geo_aliases` table maps every spelling encountered to the canonical geography id.

### 5.3 Language

- name_en / name_ne fields throughout. Nepali text stored as UTF-8 Devanagari.
- Source documents in Nepali are extracted in Nepali first, translated for name_en with human review — never auto-translated silently.

### 5.4 PDFs and messy files

- Many NRB/ministry numbers exist only in PDFs (some scanned). Pipeline: extract → load into a **staging table** → human review checklist → promote to warehouse. Nothing goes from PDF to public without review.
- Each extraction script is specific to one publication's layout and is versioned with the raw files it was built for.

### 5.5 Licensing and ethics

- Every dataset records its license/terms. World Bank, IMF, ILO data are open with attribution. Nepali government data is generally public but terms vary — record what is known, attribute everything, and link to the original source on every chart and download.
- Only published, aggregated statistics are ingested. No personal or record-level data, ever.

---

## 6. Technology decisions (with reasons)

| Decision | Choice | Why |
|---|---|---|
| Database | **PostgreSQL** | The world's most trusted open-source database; handles this model at any realistic scale; PostGIS extension powers maps. |
| Early hosting | **Supabase** (managed PostgreSQL + file storage) | No server administration needed — critical for a non-technical founder. Free tier to start; can migrate to self-hosted later because it's plain PostgreSQL underneath. |
| Pipelines | **Python** | The standard language of data work; richest libraries for APIs, Excel, PDFs. |
| Transformations | SQL, organized with **dbt** from Phase 2 | Documented, testable, repeatable transformations. |
| Orchestration | **Dagster** (Phase 4) | Schedules and monitors pipelines; overkill before automation matters. |
| API | **FastAPI** + CDN caching | Simple, fast, auto-documented. Data changes monthly, so cached responses make heavy traffic nearly free. |
| Frontend | **Next.js** + **ECharts** + GeoJSON maps | Modern, fast, huge community; ECharts handles every chart type incl. choropleth maps. |
| Code home | **GitHub** (private repo) | Version control = the project can never be lost or silently broken. |
| Map boundaries | Official Survey Department / openly licensed GeoJSON of provinces, districts, local units | Stored in the repo with provenance notes. |

Cost expectation: roughly $0–25/month until traffic grows; the architecture scales up without redesign.

---

## 7. Roadmap

**Phase 0 — Foundations (now)**
☐ This blueprint agreed · ☐ GitHub account · ☐ Supabase account · ☐ Claude Code installed (the tool Claude uses to build and run the project on your computer)

**Phase 1 — Walking skeleton (first milestone)**
One thin slice of the entire system, end to end: pull ~20 key World Bank indicators for Nepal via API → raw lake → transform → warehouse (full schema from §4) → one simple web page with a working chart. Proves every layer with the cleanest data source. *Definition of done: you open a page, pick "GDP growth", and see a correct chart with source attribution.*

**Phase 2 — Nepali sources & harmonization**
Time-period table with BS/fiscal mapping · geographies + crosswalk + aliases · NRB ingestion (Excel first, then PDF with review workflow) · Census 2021 headline tables · staging + review process. *Done: NRB inflation (BS fiscal years) and World Bank inflation (calendar years) plot correctly on one chart.*

**Phase 3 — The public portal**
Search, indicator pages, province/district choropleth maps, CSV/Excel download, public read-only API with documentation, bilingual UI. *Done: a stranger can find, understand, chart, and download a statistic without help.*

**Phase 4 — Industrial strength**
Dagster scheduling, data-quality tests (dbt tests), ingestion monitoring/alerts, revision history view, more sources (IMF, ILO, ministries), performance/caching, backups verified.

**Phase 5 — Launch & growth**
Soft launch to researchers/journalists for feedback · prioritize most-requested datasets · usage analytics · sustainability plan.

---

## 8. Working method (founder + Claude)

1. Sessions always begin by loading this blueprint (use a Claude Project so it's always in context).
2. Claude writes all code with line-by-line explanations on request; the founder runs it via Claude Code and verifies results against checklists Claude provides.
3. Every session ends with: (a) code committed to GitHub, (b) a short "project log" entry — date, what was done, what's next — kept in `PROJECT_LOG.md` alongside this blueprint.
4. Decisions that change the architecture get written into this document before being built.
5. Nothing reaches the public portal without passing the review checklist for its source type.

---

## 9. Glossary (plain language)

- **API** — a way for one program to request data from another over the internet, like a vending machine for data.
- **Ingestion** — collecting data from a source into our system.
- **Raw data lake** — the vault of untouched original files.
- **ETL / transformation** — the cleaning and standardizing step between raw files and the database.
- **Data warehouse** — the organized central database the portal reads from.
- **Schema** — the blueprint of a database: its tables and their columns.
- **Star schema** — a design with one big table of facts (numbers) linked to small lookup tables (indicators, places, periods).
- **Metadata** — data about data: source, definition, unit, license, date.
- **Vintage / release** — a snapshot of what a source published at a particular time; how revisions are tracked.
- **Crosswalk** — a mapping table between two systems (old districts ↔ new local units).
- **Choropleth map** — a map where areas are shaded by a value (e.g. literacy by district).
- **Orchestration** — software that runs pipelines automatically on schedule and reports failures.
- **CDN / caching** — keeping ready-made copies of responses so repeated requests are served instantly and cheaply.
- **GeoJSON** — a standard file format for map boundaries.
- **JSONB** — a flexible column type in PostgreSQL that holds structured labels (used for breakdowns like sex/age).

---

*End of Blueprint v1.0 — next step: Phase 0 checklist, then build the Phase 1 walking skeleton.*
