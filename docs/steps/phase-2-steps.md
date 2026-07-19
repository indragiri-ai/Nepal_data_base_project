# PHASE 2 — NEPALI SOURCES & HARMONIZATION — Step File

> **July 2026 update:** an expansion phase now sits between Phase 2 and
> Phase 3 — see **`docs/steps/phase-2b-expansion-steps.md`** (full WB mirror,
> all census topics, NRB tiers, sector portal, official 2020 map). Its
> reconciliation section marks which steps below are superseded (P2.S11) or
> partially done (P2.S4); read it before starting any step here.

**Version 1.0 — June 2026**
**Governed by: Master Prompt v1.0 · Architecture Blueprint v1.0**
**Assumes: Phase 1 exit criteria fully met (walking skeleton verified end to end — see docs/steps/phase-1-steps.md and the P1.S12 log entry).**

**Phase goal: make the portal unmistakably *Nepali*. Teach the system the two things that quietly break most Nepali datasets — the BS/AD calendar (with fiscal years) and the 2015 federal restructuring of geography — then prove it by ingesting real Nepali-source data (NRB, Census 2021) through a staging-and-review workflow, with transformations organized in dbt.**

**Why now:** Phase 1 proved every architectural layer with the cleanest possible source (World Bank: clean API, calendar years, country-level). Phase 2 faces the messy reality our model was designed for. If the universal data model, the `time_periods` "store each period once" rule, and the `is_latest` revision mechanics survive contact with NRB Excel and two calendars, the architecture is sound and every later source is repetition.

**Total founder time: ~14–20 hours across 14 steps. One step per session. Never two.**
**Phase exit criterion: you open the local web page, select an inflation chart, and see NRB inflation (Nepali fiscal years) and World Bank inflation (calendar years) plotted together on one correctly-aligned time axis — each line citing its own source — with no off-by-one-year error. And the P2.S14 checklist passes.**

**How to run every session:** open Claude Code in the project folder, open this file, and tell Claude Code: "We are on step P2.SX of docs/steps/phase-2-steps.md. Follow it under the master prompt." Approve actions one at a time; verify with the checklist; commit; log.

---

## Carry-forward lessons from Phase 1 (apply in every step)

These were logged at P1.S12 and are binding for Phase 2:

1. **Force UTF-8 stdout in every script.** Windows console defaults to cp1252 and raises on Devanagari (and even on an em-dash). P2.S1 builds a shared helper; every script that prints uses it. Phase 2 is Devanagari-heavy.
2. **Trust the `is_latest` + release model.** Re-ingestion with unchanged values keeps the prior release's row latest; a changed value inserts a new row and demotes the old. NRB revisions (P2.S12) rely on this — do not re-invent it.
3. **Raw-lake paths are keyed by the source's own code**, not our internal code. Keep this convention; document each new source's path scheme in the onboarding runbook.
4. **`.env` is the first fresh-clone tripwire.** As Phase 2 adds source keys, keep `.env.example` authoritative and update README setup.
5. **Frontend rendering needs an automated smoke test.** The chart canvas can't be eyeballed in CI. P2.S13 adds a Playwright smoke test.
6. **The two-calendar design gets its first real test now.** `time_periods` already carries `period_type`/`bs_label`; Phase 2 fills them for real.

---

### P2.S1 — The BS↔AD calendar reference (day-level)

**GOAL (plain language):** Load a lookup table that says, for every Nepali (Bikram Sambat) date, exactly which Gregorian (AD) date it is — so the system never has to *calculate* the conversion (BS month lengths are irregular and formulas get it wrong).

**WHY IT MATTERS:** Blueprint §5.1: conversions are never done by formula; a day-level table is loaded as reference data. Everything Nepali-dated in this phase depends on this table being correct.

**PREREQUISITES:** Phase 1 complete.
**TIME ESTIMATE:** 90–120 minutes.

**ACTIONS:**
1. First, build the shared UTF-8 fix (Lesson 1). Instruct Claude Code:
   > "Create `ingestion/common/io_utf8.py` with a tiny `configure_stdout_utf8()` that reconfigures stdout/stderr to UTF-8, and call it at the top of every entrypoint script. Add a one-line note to the runbook that all scripts must call it."
2. Then the calendar data. Instruct:
   > "Add a `bs_calendar` reference table via migration `0004_bs_calendar.sql` (bs_year, bs_month 1–12, bs_day, gregorian_date, weekday) covering at least BS 1970–2100 (AD ~1913–2043). Source the day-level mapping from a recognized open dataset (e.g. a well-known nepali-date dataset) — store the raw source file in the repo under `reference/calendar/` WITH a provenance note (URL, retrieval date, license), and write `scripts/load_bs_calendar.py` + `make load-calendar` that loads it idempotently. Verify, do not assume: spot-check that BS 2080-01-01 maps to the correct AD date against two independent public converters and report the result. Never guess a mapping."
3. Approve, apply, load. Have Claude Code show the row count and the two spot-checks.

**VERIFICATION CHECKLIST:**
- [ ] `make migrate-status` shows 0004 applied; `bs_calendar` has tens of thousands of rows (≈ one per day).
- [ ] Two independent converters agree with our table on at least three sample dates (incl. a fiscal-year boundary date, ~mid-July).
- [ ] The raw calendar source file sits in `reference/calendar/` with a provenance note.
- [ ] Every new script prints Devanagari without error (UTF-8 helper works).

**IF IT GOES WRONG:** A mismatch on spot-checks → the source dataset is suspect; try a second recognized source and reconcile before loading. This table is foundational — correctness here is non-negotiable.

**COMMIT:** `P2.S1: BS↔AD day-level calendar reference (0004) + UTF-8 stdout helper`

---

### P2.S2 — Fiscal-year and BS time periods

**GOAL (plain language):** Create the Nepali period rows — each fiscal year (Shrawan→Ashadh, ≈ mid-July to mid-July) and each BS year — in the SAME `time_periods` table the World Bank calendar years already live in, each stored once with exact Gregorian start/end dates and proper BS/fiscal labels.

**WHY IT MATTERS:** Blueprint §5.1: data attaches to periods, never to bare year numbers. This is what later lets "FY 2080/81", "2024 calendar", and "Q3 2024" share one true time axis. It directly enables the phase's exit milestone.

**PREREQUISITES:** P2.S1.
**TIME ESTIMATE:** 60–90 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Using `bs_calendar`, seed `time_periods` rows of `period_type='fiscal_year'` for Nepali FYs spanning our data era (e.g. FY 2030/31 BS onward, ≈1973 AD → present): gregorian_start = the Shrawan-1 AD date, gregorian_end = the next Ashadh-end AD date, bs_label like '2080/81', gregorian_label like 'FY 2023/24', sort_key chronological and interleaving correctly with the existing calendar-year rows. Also seed `period_type='fiscal_year'` uniqueness must hold. Add `make seed-periods-ne`, idempotent. Keep the existing calendar-year periods untouched."
2. Have Claude Code print, side by side, the calendar-year row and the fiscal-year row that overlap a given AD year, showing their distinct start/end dates and sort_keys — so you can SEE there is no collision and the ordering is right.

**VERIFICATION CHECKLIST:**
- [ ] `time_periods` now holds calendar-year AND fiscal-year rows; re-running the seed changes no counts (idempotent).
- [ ] A fiscal year's gregorian_start/end straddle two calendar years (mid-July to mid-July), proven by a printed example.
- [ ] sort_key orders a fiscal year correctly relative to the calendar years around it.

**IF IT GOES WRONG:** Off-by-one on the fiscal boundary (Shrawan 1 vs Ashadh end) → recompute from `bs_calendar` exact dates, never from "mid-July" as a guess.

**COMMIT:** `P2.S2: fiscal-year and BS time periods (one axis, stored once)`

---

### P2.S3 — dbt project: transformations become documented and tested

**GOAL (plain language):** Stand up dbt — the tool that turns our SQL transformations into version-controlled, documented, automatically-tested steps — and rebuild one existing view (the API's "latest observations" read) as the first dbt model, so the pattern is proven before the messy data arrives.

**WHY IT MATTERS:** Blueprint §6 / Master Prompt: transformations are organized with dbt from Phase 2. Introducing it now, on data we already trust, means the NRB/Census steps plug into a working, tested transformation layer instead of inventing one under pressure.

**PREREQUISITES:** P2.S2.
**TIME ESTIMATE:** 90–120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Initialize a dbt project under `transform/` against our Postgres (profiles read DATABASE_URL from `.env`, never committed). Create a `staging` and a `marts` layer. As the first model, express the current is_latest series read used by the API as a dbt model `marts.fct_observations_latest`, with dbt schema tests: not_null on keys, relationships (FKs) to dimensions, and a uniqueness test on (indicator, geography, time_period, breakdowns) among is_latest rows. Add `make dbt-run` and `make dbt-test`. Add a dbt docs note. Do NOT yet repoint the API at it — just prove the model builds and tests pass."
2. Run `make dbt-run` then `make dbt-test`. Read the test summary together.

**VERIFICATION CHECKLIST:**
- [ ] `make dbt-run` builds the model; `make dbt-test` passes (uniqueness + not_null + relationships).
- [ ] dbt profile reads DATABASE_URL from `.env`; `git status` shows no secret committed.
- [ ] `make test` (pytest) still green.

**IF IT GOES WRONG:** dbt can't connect → it's the profile/DSN; have Claude Code print the resolved host (not the password) and fix. Test failures on real data → that's dbt doing its job; investigate the row it names before moving on.

**COMMIT:** `P2.S3: dbt project with first tested mart model`

---

### P2.S4 — Geography master: the new (post-2015) structure

**GOAL (plain language):** Load Nepal's current administrative geography — 7 provinces, 77 districts, 753 local units — into the `geographies` table with the correct parent/child hierarchy and validity dates, each row carrying its source.

**WHY IT MATTERS:** Blueprint §5.2: data is stored against the boundaries it was published in. Census 2021 and current NRB/administrative data use the new structure; it must exist before that data lands.

**PREREQUISITES:** P2.S3.
**TIME ESTIMATE:** 90–120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Create seed files in `db/seeds/geo/` for the post-2015 structure: 7 provinces, 77 districts, 753 local units (rural/urban municipalities), with name_en and name_ne (Devanagari), level, parent_id hierarchy (local unit → district → province → country), valid_from = 2015-09-20 (constitution promulgation), code scheme documented. Source from an openly-licensed official list (Survey Department / official local-unit list); store the raw source under `reference/geo/` with provenance. Load via `make seed-geo-new`, idempotent. Verify counts against the official totals (7/77/753) and report any discrepancy rather than padding."
2. Spot-check: have Claude Code print one full chain (a named local unit → its district → its province → Nepal) with Devanagari names.

**VERIFICATION CHECKLIST:**
- [ ] Counts exactly: 7 provinces, 77 districts, 753 local units; idempotent on re-run.
- [ ] One printed parent chain reads correctly in both English and Devanagari.
- [ ] Raw source + provenance note present in `reference/geo/`.

**IF IT GOES WRONG:** Count mismatch (e.g. 752/753) → a known data-source omission; find the missing unit from the official list, never invent one. Report the fix.

**COMMIT:** `P2.S4: geography master — new (post-2015) structure`

---

### P2.S5 — Geography master: the old (pre-2015) structure

**GOAL (plain language):** Load the pre-2015 geography — 5 development regions, 75 districts — also into `geographies`, with validity dates that close in 2015, so older data (Census 2011, historical series) has correct boundaries to attach to.

**WHY IT MATTERS:** Blueprint §5.2: comparison across the 2015 break is only honest if both worlds exist as first-class geographies and nothing is silently mapped.

**PREREQUISITES:** P2.S4.
**TIME ESTIMATE:** 60–90 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Seed the pre-2015 structure into `geographies`: 5 development regions, 75 districts (level=old_region/old_district per our P1.S4 CHECK), name_en/name_ne, valid_from (historical) and valid_to = 2015-09-19. Keep codes distinct from the new structure. Source + provenance under `reference/geo/`. `make seed-geo-old`, idempotent. Note clearly that 14 zones are intentionally omitted unless a real dataset needs them (avoid loading reference data no source uses — Prime Directive 7)."
2. Verify the old and new sets coexist without code or uniqueness collisions.

**VERIFICATION CHECKLIST:**
- [ ] 5 development regions + 75 old districts present, validity ending 2015-09-19; new structure unchanged.
- [ ] No code collision between old and new geographies; idempotent.
- [ ] You can state in one sentence why both structures exist at once.

**IF IT GOES WRONG:** Tempted to map old→new here — don't. That is the crosswalk's job (next step), kept deliberately separate.

**COMMIT:** `P2.S5: geography master — old (pre-2015) structure`

---

### P2.S6 — The geography crosswalk and aliases

**GOAL (plain language):** Build the two tables that connect the messy real world to our clean geography: a crosswalk mapping old areas to new ones (for careful cross-2015 comparison) and an alias table mapping every spelling variant of a place name to the one canonical geography.

**WHY IT MATTERS:** Blueprint §5.2: crosswalked figures must be flagged "estimated via boundary mapping," and place-name spellings vary wildly across sources — `geo_aliases` is what lets a pipeline resolve "Kathmandu"/"Kathmandu"/"काठमाडौं"/"Kathmandu Metropolitan" to one id without guessing.

**PREREQUISITES:** P2.S5.
**TIME ESTIMATE:** 90–120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Migration `0005_geo_crosswalk.sql`: `geography_crosswalk` (from_geography_id, to_geography_id, relationship in [same, split, merged, partial], weight numeric nullable for partial areas, method_note, source) and `geo_aliases` (alias_text, geography_id, source, UNIQUE(alias_text)). Seed the crosswalk for at least the district-level old→new mapping where well-established (most 75→77 are stable; document the known splits), and seed `geo_aliases` with the English+Devanagari names of every geography plus common romanization variants. Add a resolver `ingestion/common/geo_resolve.py: resolve(name) -> geography_id | None` that consults aliases and returns None (never a guess) on miss, logging the unmatched string. `make seed-geo-crosswalk`. Document the 'estimated via boundary mapping' flag contract for the API/frontend."
2. Test the resolver: feed it three correct spellings and one deliberately unknown string; confirm three resolve and the unknown returns None and is logged.

**VERIFICATION CHECKLIST:**
- [ ] `0005` applied; crosswalk and aliases seeded; idempotent.
- [ ] Resolver maps known spellings (incl. one Devanagari) to the right id and returns None on the unknown (no silent guess).
- [ ] The "estimated via boundary mapping" flag rule is written down for later display.

**IF IT GOES WRONG:** A district split with no clean mapping (e.g. an area divided) → record it as `partial` with a weight and a method_note; do not force a 1:1.

**COMMIT:** `P2.S6: geography crosswalk + aliases + resolver`

---

### P2.S7 — Onboard NRB: raw acquisition of the first Excel

**GOAL (plain language):** Bring in the first real Nepali source. Download an actual Nepal Rastra Bank Excel publication (the CPI / inflation table) and store the untouched file in the raw lake with its fingerprint and source URL — before any parsing.

**WHY IT MATTERS:** Blueprint principle 2 + §5.4: raw is immutable, stored before parsing; this is the source whose fiscal-year inflation will meet the World Bank's calendar-year inflation at the phase finale.

**PREREQUISITES:** P2.S6.
**TIME ESTIMATE:** 60–90 minutes.

**ACTIONS:**
1. Walk the source-onboarding runbook (`docs/runbooks/adding-a-data-source.md`) for NRB. Instruct Claude Code:
   > "Register NRB as a `source` and the CPI publication as a `dataset` (access_method=file) via a seed. Then write `ingestion/nrb/acquire.py` that downloads the specific NRB CPI Excel from its official URL and stores it via the raw-lake helper at `nrb/<dataset>/<utc-stamp>/payload.xlsx` with metadata (sha256, fetched_at, source_url, size). `make nrb-acquire`. If the file is behind a manual download, support a `--from-file` path so the founder can supply the downloaded file, and store THAT with provenance. Record the exact source URL and retrieval date."
2. Run it (or supply the file). Confirm the object and its metadata sidecar in Supabase Storage.

**VERIFICATION CHECKLIST:**
- [ ] NRB source + CPI dataset rows exist; raw `.xlsx` stored with sha256 + source_url metadata.
- [ ] Raw-lake path follows the documented NRB scheme (Lesson 3).
- [ ] The exact source URL + retrieval date are recorded (in dataset/provenance).

**IF IT GOES WRONG:** NRB site blocks automated download → use `--from-file` with the founder's manual download; the immutability + provenance guarantee is identical.

**COMMIT:** `P2.S7: NRB onboarding — raw CPI Excel acquired`

---

### P2.S8 — Parse NRB CPI into a staging table

**GOAL (plain language):** Read the NRB Excel — built for one specific sheet layout — and load its numbers into a *staging* table (a holding area), mapped to our fiscal-year periods and geography, but NOT yet promoted to the public warehouse.

**WHY IT MATTERS:** Blueprint §5.4: messy-file pipeline is extract → staging → human review → promote. Nothing goes from a spreadsheet to the public without a review gate. The extraction script is specific to this publication's layout and versioned with the raw file it was built for.

**PREREQUISITES:** P2.S7.
**TIME ESTIMATE:** 90–120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Migration `0006_staging.sql`: a `staging_observations` table mirroring observation fields plus `raw_file_ref`, `review_status` (pending/approved/rejected), `review_note`, `extracted_by_script`. Then `ingestion/nrb/cpi_pipeline.py`: read the raw CPI Excel from the lake with openpyxl, locate the inflation series by its known sheet/cell layout (documented in comments, versioned to this file), map each Nepali fiscal year → our fiscal_year time_period (via labels/bs_calendar), value→numeric, resolve geography to Nepal (national CPI), and INSERT into staging with review_status='pending'. Run the existing quality gate (P1.S9) in staging mode. Add a saved sample fixture so parsing is unit-tested offline. `make nrb-cpi-stage`."
2. Run it; have Claude Code print a few staged fiscal-year/value rows and the quality-gate result.

**VERIFICATION CHECKLIST:**
- [ ] `0006` applied; staging populated with NRB CPI rows mapped to fiscal-year periods; nothing in `observations` yet.
- [ ] Parsing is covered by an offline fixture test; `make test` green.
- [ ] Quality gate ran on the staged rows and reported sensibly.

**IF IT GOES WRONG:** The sheet layout differs from expectation (merged cells, header rows) → adjust the extractor to the real layout and document the actual cell map; never hard-code a value to "make it work."

**COMMIT:** `P2.S8: NRB CPI extraction into staging`

---

### P2.S9 — The human review gate: promote staging to warehouse

**GOAL (plain language):** Build the review checklist and the one-command promotion that moves approved staging rows into the real `observations` table under a proper release — and proves that un-reviewed data physically cannot reach the public.

**WHY IT MATTERS:** Blueprint §5.4: nothing goes from PDF/Excel to public without review. This gate is the trust boundary for every messy Nepali source from here on.

**PREREQUISITES:** P2.S8.
**TIME ESTIMATE:** 90–120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Build a review workflow: `scripts/review_staging.py` that lists pending staged rows with their values and source, lets the reviewer approve/reject a batch (CLI prompts or a review note file), and `ingestion/common/promote.py` that, for approved rows only, creates a `releases` row and inserts them into `observations` (letting is_latest mechanics apply), writing a full ingestion_log. Rejected rows stay in staging with a reason. A row with review_status='pending' must never be promotable. `make review` and `make promote`. Document the reviewer checklist (does the number match the source PDF/Excel cell? right fiscal year? right unit? plausible?) in the runbook."
2. Walk one real review: approve the NRB CPI rows after eyeballing two values against the source file, promote, and confirm they now appear in `observations` and via the API.

**VERIFICATION CHECKLIST:**
- [ ] Approved NRB CPI rows appear in `observations` under a new release; pending/rejected rows do not.
- [ ] A deliberate attempt to promote a still-pending row is refused.
- [ ] `/v1/data?indicator=NRB_CPI…&geo=NP` returns the series with provenance citing NRB.

**IF IT GOES WRONG:** A value doesn't match the source on review → reject with a note; the point of the gate is that this is caught here, by a human, not in public.

**COMMIT:** `P2.S9: staging review gate + promotion to warehouse`

---

### P2.S10 — NRB monetary aggregates and forex (reuse the pattern)

**GOAL (plain language):** Add two more NRB tables — broad money / monetary aggregates and foreign-exchange reserves — by reusing the acquire → stage → review → promote pattern, proving the workflow generalizes beyond one table.

**WHY IT MATTERS:** Master Prompt: after the first messy source, additional ones should be *repetition of a proven pattern, not new invention*. This is the test of that claim.

**PREREQUISITES:** P2.S9.
**TIME ESTIMATE:** 90–120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Add the NRB monetary-aggregates and forex-reserves publications as datasets; write their acquire + extraction-into-staging scripts (layout-specific, versioned), reusing raw-lake, the quality gate, staging, and the review/promote workflow unchanged. Seed any new indicators/units they need via the seed files (not on the fly — Prime Directive 7). `make nrb-money-stage` / `make nrb-forex-stage`. Offline fixtures for each parser."
2. Review and promote both; spot-check one value of each against the NRB source.

**VERIFICATION CHECKLIST:**
- [ ] Two more NRB series live in `observations` via the same review→promote path; provenance cites NRB.
- [ ] New indicators/units came from versioned seeds, not inline inserts.
- [ ] `make test` green with the new fixtures; no change was needed to the core staging/promote code (only new layout-specific extractors).

**IF IT GOES WRONG:** If a new table forces a change to the *core* workflow (not just its extractor), pause — that's a sign the abstraction from P2.S8–S9 needs adjusting; fix it there, not with a special case.

**COMMIT:** `P2.S10: NRB monetary aggregates and forex via the staging pattern`

---

### P2.S11 — Census 2021 headline tables

**GOAL (plain language):** Ingest Census 2021 headline numbers — population, literacy, and households by province and district — against the new geography, through the same staging-and-review gate.

**WHY IT MATTERS:** Census is the backbone reference dataset for Nepal; getting its province/district figures in correctly (new boundaries, Devanagari names, the geo resolver) exercises the entire geography stack built in P2.S4–S6.

**PREREQUISITES:** P2.S10.
**TIME ESTIMATE:** 120 minutes (the data-heaviest step — start fresh).

**ACTIONS:**
1. Instruct Claude Code:
   > "Onboard the Census 2021 (NSO/CBS) source + dataset. Acquire the headline tables (population, literacy rate, household counts by province and district) into the raw lake. Write a layout-specific extractor that maps each area name to a geography_id via the P2.S6 resolver (unmatched names are logged and reported, never guessed), maps the census reference period to the right time_period, and loads to staging. Review and promote. Seed the census indicators (POP_CENSUS, LITERACY_CENSUS, HOUSEHOLDS…) via seed files. Offline fixture test."
2. Review carefully (geography is where census errors hide); promote; verify a province total roughly equals the sum of its districts.

**VERIFICATION CHECKLIST:**
- [ ] Census population/literacy/households present by province and district, against post-2015 geographies; provenance cites the census.
- [ ] Every area name resolved via aliases (the unmatched-name log is empty or each entry explained).
- [ ] A province's value ≈ sum of its districts (sanity), shown by a query.

**IF IT GOES WRONG:** Unresolved place names → add the spelling to `geo_aliases` with its source and re-run; do not hand-map in the pipeline.

**COMMIT:** `P2.S11: Census 2021 headline tables by province and district`

---

### P2.S12 — Prove revision handling with a real NRB revision

**GOAL (plain language):** Take a figure NRB actually revised (a provisional value later restated), ingest the revised release, and show that the old value is preserved while the new one becomes the default — exactly the `is_latest` promise, now demonstrated on real Nepali data.

**WHY IT MATTERS:** Quality Bar: "NRB revised this figure" must be expressible without ever overwriting history. Phase 1 proved the mechanism on synthetic data; this proves it where it matters.

**PREREQUISITES:** P2.S11.
**TIME ESTIMATE:** 60–90 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Identify a real NRB value that was published provisional then revised (or simulate faithfully from two genuine NRB releases). Acquire the revised file (new raw object), stage, review, and promote as a NEW release for the same indicator/geography/period. Then show: the prior observations row now is_latest=false with its original value intact, the new row is_latest=true, and the API returns the revised value while the history remains queryable. Add a small query/endpoint or note showing how to retrieve the revision history of a cell."
2. Walk the before/after with Claude Code; confirm nothing was overwritten.

**VERIFICATION CHECKLIST:**
- [ ] Two rows exist for the revised cell: old (is_latest=false, original value) and new (is_latest=true, revised value).
- [ ] The API/default view shows the revised value; the original is still retrievable.
- [ ] The traceability drill still works for the revised number (chart → release → raw → source).

**IF IT GOES WRONG:** The new value overwrote instead of revising → the release wasn't distinct or the trigger path was bypassed; fix before proceeding — this is the heart of the trust model.

**COMMIT:** `P2.S12: revision handling proven on a real NRB revision`

---

### P2.S13 — The alignment milestone: two calendars on one axis

**GOAL (plain language):** The payoff. Make the chart page able to draw NRB inflation (Nepali fiscal years) and World Bank inflation (calendar years) together on one correctly-aligned time axis, each line citing its own source, with a boundary-vintage flag where relevant — and add an automated test so the chart's rendering is provable, not just eyeballed.

**WHY IT MATTERS:** This is the phase exit criterion made visible, and the whole reason the `time_periods` "store each period once with exact Gregorian dates" rule exists. If the two series align with no off-by-one-year error, Phase 2's hardest claim is proven.

**PREREQUISITES:** P2.S12.
**TIME ESTIMATE:** 120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Extend the API so a series response carries each observation's exact gregorian_start/end and period_type, and so multiple indicators can be requested for one chart. In the Next.js app, add an inflation view that plots NRB CPI (fiscal_year) and World Bank CPI (calendar year) on a shared time axis positioned by the periods' true Gregorian dates (fiscal years sit mid-year, not on Jan 1), each line labeled and citing its own source beneath, with the 'estimated via boundary mapping' flag shown if any crosswalked geography is used. Then add a Playwright smoke test (Lesson 5) that loads the page, selects this view, and asserts the chart canvas and both source citations render."
2. Run `make api` + `make web`; open the inflation view. Confirm with your eyes that the two series align sensibly across years (no full-year offset), then run the Playwright test.

**VERIFICATION CHECKLIST:**
- [ ] NRB (FY) and World Bank (calendar) inflation appear together, aligned by true Gregorian dates, no off-by-one-year error.
- [ ] Each line cites its own source; crosswalk flag appears when applicable.
- [ ] `make web-test` (Playwright smoke) passes; `make test` + `make dbt-test` green.

**IF IT GOES WRONG:** The fiscal series looks shifted a year → the axis is using bare year labels instead of the periods' gregorian_start; position by real dates. This is THE bug the phase exists to catch.

**COMMIT:** `P2.S13: NRB + World Bank inflation aligned on one axis (the Nepali milestone)`

---

### P2.S14 — Phase close: prove it, document it, log it

**GOAL (plain language):** Verify the Nepali-harmonization slice holds together end to end, refresh the rebuild and traceability drills with the new sources, update docs, and formally close Phase 2.

**WHY IT MATTERS:** A phase is done only when the whole is verified (Master Prompt §3.7). Phase 2 added calendars, two geographies, a review gate, dbt, and three real Nepali sources — the drills must still pass with all of it.

**PREREQUISITES:** P2.S1–S13.
**TIME ESTIMATE:** 60–90 minutes.

**ACTIONS:**
1. Rebuild drill — instruct Claude Code:
   > "Following ONLY the README, from a fresh-clone simulation, run the full Phase 2 chain (calendar load → periods → geo seeds → crosswalk → dbt → NRB acquire/stage/review/promote → census → web) and report every place the README is unclear or wrong. Fix the README."
2. Traceability drill on a Nepali number — instruct:
   > "Trace one NRB inflation value: chart → API → observations row → release → staging row → raw Excel object + source URL, and time it. It must complete in under a minute and show the human-review step in the chain."
3. Phase exit checklist below; dbt docs note; PROJECT_LOG entry with lessons for Phase 3 (the public-portal design phase); final commit.

**VERIFICATION CHECKLIST (= PHASE 2 EXIT CRITERIA):**
- [ ] Inflation milestone (P2.S13) holds: two calendars, one aligned axis, both cited.
- [ ] Fresh-start drill completes from README alone, including the review gate.
- [ ] Traceability drill on an NRB number completes in under a minute and includes the review step.
- [ ] `make test`, `make lint`, `make dbt-test`, and the Playwright smoke test all green; migrations 0004–0006 applied.
- [ ] All Phase 2 commits pushed to GitHub.
- [ ] You can explain to a friend why "FY 2080/81" and "2024" sit correctly on one chart, and what the review gate protects.
- [ ] PROJECT_LOG.md closes the phase with lessons-for-Phase-3 noted.

**IF IT GOES WRONG:** Anything failing here failed on 3 sources instead of 30 — fix forward, re-run the drills.

**COMMIT:** `P2.S14: phase 2 closed — Nepali sources & harmonization verified`

---

## After Phase 2

Say to Claude (in the Claude Project, with the PROJECT_LOG lessons at hand): **"Phase 2 exit criteria met — generate the Phase 3 step file."** Phase 3 is *The Public Portal*: the design system, information architecture, the §3.6 chart framework, choropleth maps with drill-down, CSV/Excel downloads, the public API docs page, bilingual UI, and a soft deployment — turning this proven engine into something a stranger can find, understand, chart, and download unaided.
