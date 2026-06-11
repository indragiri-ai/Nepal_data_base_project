# PHASE 1 — WALKING SKELETON — Step File

**Version 1.0 — June 2026**
**Governed by: Master Prompt v1.0 · Architecture Blueprint v1.0**
**Assumes: Phase 0 exit criteria fully met (see docs/steps/phase-0-steps.md).**

**Phase goal: one thin, working slice of the ENTIRE system — about 20 headline World Bank indicators for Nepal flowing through every layer: ingestion → raw lake → warehouse (full professional schema) → API → an interactive, source-cited chart in your browser.**

**Why a skeleton first:** it proves every architectural decision with the cleanest data source before we face the messy ones. After this phase, adding NRB or census data is repetition of a proven pattern, not new invention.

**Total founder time: ~10–14 hours across 12 steps. One step per session. Never two.**
**Phase exit criterion: you open a local web page, select "GDP growth (annual %)", and see a correct, interactive chart citing the World Bank — and the P1.S12 checklist passes.**

**How to run every session:** open Claude Code in the `nepal-data-portal` folder, open this file, and tell Claude Code: "We are on step P1.SX of docs/steps/phase-1-steps.md. Follow it under the master prompt." Approve actions one at a time; verify with the checklist; commit; log.

---

### P1.S1 — Local development environment

**GOAL (plain language):** Install the languages and helper tools the project runs on (Python for data work, Node.js for the website) and the quality tools that keep code clean, with one-command shortcuts.

**WHY IT MATTERS:** Master Prompt §3.3 requires formatted, linted, type-checked, tested code. Installing the toolchain once, properly, means every later step starts instantly.

**PREREQUISITES:** Phase 0 complete.
**TIME ESTIMATE:** 60–90 minutes (mostly waiting for installers).

**ACTIONS:**
1. In Claude Code (in the repo folder), instruct:
   > "Set up the development environment per Master Prompt §3.3: check whether Python 3.12+ and Node.js LTS are installed; if not, guide me through installing them for my operating system, one screen at a time. Then create the Python project: `pyproject.toml` with pinned dependencies (start with: requests, psycopg, python-dotenv, pytest, ruff, mypy, yoyo-migrations), a virtual environment, and a `Makefile` with targets: `make setup` (install deps), `make test` (pytest), `make lint` (ruff + mypy), `make fmt` (ruff format). Update README.md's 'how to run' section. Explain each file you create in one plain sentence."
2. Approve and follow its guidance. When it finishes, run the handshake: ask Claude Code to run `make lint` and `make test` (tests will report "no tests ran" — that's expected and fine at this stage).
3. Ask Claude Code: "Show me the pyproject.toml and explain what 'pinned dependencies' protects us from." (Answer you should hear: surprise breakage when a library updates.)

**VERIFICATION CHECKLIST:**
- [ ] `make lint` runs and reports success (or only explains there's no code yet).
- [ ] `make test` runs (zero tests collected is fine).
- [ ] README.md now contains setup instructions.
- [ ] You can say, in one sentence each, what Python, Node.js, and the Makefile are for. (If not, ask Claude Code to explain until you can — this is part of the step.)

**IF IT GOES WRONG:** Installer/PATH problems are the classic first-day issue. Paste the exact error to Claude Code; if stuck >30 min, stop, log "stopped mid-P1.S1 after action N", and resume fresh next session.

**COMMIT:** `P1.S1: development environment and tooling`

---

### P1.S2 — Secure connection to the database

**GOAL (plain language):** Let code on your computer talk to your Supabase PostgreSQL database — with the password kept in a local secrets file that can never reach GitHub.

**WHY IT MATTERS:** Prime Directive 5: secrets never in code. This step builds the habit and the plumbing at the same time.

**PREREQUISITES:** P1.S1.
**TIME ESTIMATE:** 30–45 minutes.

**ACTIONS:**
1. In the Supabase dashboard: Project Settings → Database → copy the connection string (URI format). It contains your database password — treat the whole string as a secret.
2. In Claude Code, instruct:
   > "Create a `.env` file (git-ignored — verify .gitignore covers it BEFORE creating) with a `DATABASE_URL=` line; I will paste the value into the file myself in my text editor, not into this chat. Then create `scripts/check_db.py` that loads `.env`, connects to the database, and prints the PostgreSQL version and the current time from the server, with a clear success/failure message. Add `make check-db` to the Makefile."
3. Open `.env` yourself in any text editor and paste the connection string after `DATABASE_URL=`. Save.
4. Ask Claude Code to run `make check-db`.
5. Critical safety verification: ask Claude Code to run `git status` and confirm `.env` does NOT appear as a file to be committed.

**VERIFICATION CHECKLIST:**
- [ ] `make check-db` prints a PostgreSQL version (e.g. "PostgreSQL 16.x") and a timestamp.
- [ ] `git status` does not list `.env`.
- [ ] `.env.example` (committed) shows the variable name with a dummy value only.

**IF IT GOES WRONG:**
- Connection refused/timeout → most often a copy-paste error in the URL or a network firewall; re-copy from Supabase, try again.
- `.env` shows in git status → STOP. Tell Claude Code: "Fix .gitignore to exclude .env and verify it is untracked." If it was ever committed and pushed, rotate the database password in Supabase immediately (Prime Directive 5).

**COMMIT:** `P1.S2: database connectivity check (secrets kept local)`

---

### P1.S3 — Migration tooling + the provenance spine (migration 0001)

**GOAL (plain language):** Set up the system that applies database changes as numbered, versioned files — then use it to create the first four tables: the ones that record *where every number comes from*.

**WHY IT MATTERS:** Master Prompt §3.2: schema changes happen ONLY through migrations. Starting with `sources`, `datasets`, `releases`, `ingestion_log` makes provenance — the soul of the portal — physically primary: data tables will literally be unable to exist without reference to them.

**PREREQUISITES:** P1.S2.
**TIME ESTIMATE:** 60–90 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Configure yoyo-migrations to run plain-SQL migration files from `db/migrations/` against DATABASE_URL. Then write migration `0001_provenance.sql` creating, per Blueprint §4.2 and Master Prompt §3.2 standards (snake_case, NOT NULL by default, declared FKs, timestamptz created_at/updated_at, CHECK constraints for enums): `sources`, `datasets` (FK→sources, CHECK on access_method in api/file/scrape/manual), `releases` (FK→datasets), `ingestion_log` (FK→datasets, status CHECK in running/success/failed, columns for started/finished, rows_in, rows_loaded, rows_rejected, raw_file_refs, error_note). Include a rollback section per yoyo convention. Add `make migrate` and `make migrate-status`. Before applying, show me the SQL with a plain-language walkthrough, table by table."
2. Read the walkthrough. You should be able to say what each table is for in one sentence. Ask until you can.
3. Approve; Claude Code applies the migration.
4. Verify in the Supabase dashboard Table Editor: the four tables exist (plus yoyo's own bookkeeping table — that's normal).

**VERIFICATION CHECKLIST:**
- [ ] `make migrate-status` shows 0001 as applied.
- [ ] Supabase Table Editor shows `sources`, `datasets`, `releases`, `ingestion_log`, all empty.
- [ ] The migration file exists in `db/migrations/` and is committed.
- [ ] You can state the one-sentence purpose of each table.

**IF IT GOES WRONG:** A migration that fails mid-way: tell Claude Code to show the error, fix the SQL, roll back if partially applied, and re-apply. Because the database is empty, nothing can be lost in this phase.

**COMMIT:** `P1.S3: migration tooling and provenance tables (0001)`

---

### P1.S4 — Dimension tables (migration 0002)

**GOAL (plain language):** Create the lookup tables that give every number its meaning: what is measured (indicators), in what unit, where (geographies), and when (time periods).

**WHY IT MATTERS:** This is the "one universal data model" (Blueprint §2.1) taking physical form. Every future dataset — census, NRB, ministries — will plug into these same four tables.

**PREREQUISITES:** P1.S3.
**TIME ESTIMATE:** 60–90 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Write and apply migration `0002_dimensions.sql` per Blueprint §4.2: `units` (code, name_en, name_ne, notes); `indicators` (stable unique `code`, name_en, name_ne, definition_en, definition_ne, FK unit_id, topic CHECK constraint per blueprint topics, source_concept, FK preferred_source_id→sources, nullable); `geographies` (code unique, name_en, name_ne, level CHECK in country/province/district/local_unit/old_region/old_district, self-FK parent_id nullable, valid_from, valid_to nullable, geometry_ref nullable); `time_periods` (period_type CHECK in year/fiscal_year/quarter/month/census_round, gregorian_start, gregorian_end, bs_label nullable, gregorian_label, sort_key, with a uniqueness constraint on (period_type, gregorian_start, gregorian_end)). name_ne columns must accept Devanagari — include a comment noting UTF-8. Same review procedure: plain-language walkthrough before applying."
2. Review, approve, apply.
3. Devanagari smoke test — instruct: "Insert one throwaway row into geographies with name_ne='नेपाल', select it back and show me, then delete it." Confirm the script displays नेपाल correctly.

**VERIFICATION CHECKLIST:**
- [ ] `make migrate-status` shows 0001 and 0002 applied.
- [ ] Table Editor shows the four new tables.
- [ ] The Devanagari round-trip displayed नेपाल correctly.

**IF IT GOES WRONG:** Same migration recovery as P1.S3. Mojibake (garbled Devanagari) → tell Claude Code; it's an encoding setting, fixable in minutes, and far better caught now than in Phase 2.

**COMMIT:** `P1.S4: dimension tables (0002)`

---

### P1.S5 — The observations fact table (migration 0003)

**GOAL (plain language):** Create the single big table where every statistic in the entire portal will live — with the database itself enforcing the rules that make revisions safe and duplicates impossible.

**WHY IT MATTERS:** This is the heart (Blueprint §4.2/§4.3). The uniqueness constraint and `is_latest` mechanics built here are what later let us say "NRB revised this figure" without ever overwriting history.

**PREREQUISITES:** P1.S4.
**TIME ESTIMATE:** 60–90 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Write and apply migration `0003_observations.sql`: table `observations` with FKs to indicators, geographies, time_periods, datasets, releases; `value numeric NOT NULL` (never float — Master Prompt §3.2); FK unit_id; `breakdowns jsonb NOT NULL DEFAULT '{}'`; `status` CHECK in provisional/revised/final/estimated; `is_latest boolean NOT NULL DEFAULT true`; `footnote text`; timestamps. Enforce the Blueprint §4.2 uniqueness: UNIQUE (indicator_id, geography_id, time_period_id, breakdowns, release_id). Add indexes serving the API's main query pattern (indicator+geography+period, and is_latest filtering), each with a comment naming the query it serves. Also create a trigger or documented application-side procedure ensuring that when a new release inserts an observation for the same (indicator, geography, period, breakdowns), older rows get is_latest=false — explain to me the option you choose and why, before applying."
2. Listen to the trigger-vs-application-logic explanation and its recommendation; approve.
3. Apply; review walkthrough as always.

**VERIFICATION CHECKLIST:**
- [ ] Migration 0003 applied; `observations` visible in Table Editor.
- [ ] Ask Claude Code to attempt inserting the same observation twice for the same release using test rows — the database itself must reject the duplicate. Then have it clean up the test rows.
- [ ] You can explain `is_latest` in one sentence. (Suggested: "the newest published value wins the default view, but old values are never deleted.")

**IF IT GOES WRONG:** Standard migration recovery. If the duplicate test does NOT fail, the constraint is wrong — fix via a new migration before proceeding (never edit 0003 after commit; Master Prompt §3.2).

**COMMIT:** `P1.S5: observations fact table with revision mechanics (0003)`

---

### P1.S6 — Seed the reference data

**GOAL (plain language):** Load the foundational facts the pipeline needs: Nepal as a geography, calendar years 1960–2030 as time periods, the units, the World Bank as a source, and the definitions of our first ~20 indicators.

**WHY IT MATTERS:** Pipelines must never invent reference data on the fly (Prime Directive 7) — indicators and geographies are curated by humans, in version-controlled seed files. This step also fixes our launch indicator list.

**PREREQUISITES:** P1.S5.
**TIME ESTIMATE:** 60–90 minutes.

**The Phase 1 indicator list** (World Bank WDI codes; the seed step verifies each against the live API and flags any retired code instead of guessing):
GDP, current US$ `NY.GDP.MKTP.CD` · GDP growth, annual % `NY.GDP.MKTP.KD.ZG` · GDP per capita, US$ `NY.GDP.PCAP.CD` · Inflation, CPI annual % `FP.CPI.TOTL.ZG` · Population `SP.POP.TOTL` · Population growth % `SP.POP.GROW` · Life expectancy `SP.DYN.LE00.IN` · Infant mortality `SP.DYN.IMRT.IN` · Adult literacy % `SE.ADT.LITR.ZS` · School enrollment, primary `SE.PRM.ENRR` · Unemployment % (ILO est.) `SL.UEM.TOTL.ZS` · Personal remittances received, US$ `BX.TRF.PWKR.CD.DT` · Remittances, % of GDP `BX.TRF.PWKR.DT.GD.ZS` · Exports, % of GDP `NE.EXP.GNFS.ZS` · Imports, % of GDP `NE.IMP.GNFS.ZS` · Total reserves, US$ `FI.RES.TOTL.CD` · Urban population % `SP.URB.TOTL.IN.ZS` · Access to electricity % `EG.ELC.ACCS.ZS` · Internet users % `IT.NET.USER.ZS` · Foreign direct investment, net inflows US$ `BX.KLT.DINV.CD.WD`

**ACTIONS:**
1. Instruct Claude Code:
   > "Create seed files in `db/seeds/` (CSV or SQL, your recommendation) and a `make seed` target that loads them idempotently (running twice must not duplicate): (a) geography: Nepal, level=country, code=NP, name_ne=नेपाल; (b) time_periods: calendar years 1960–2030 with correct gregorian_start/end, gregorian_label, sort_key; (c) units needed by the indicator list (US$, %, persons, years, etc.); (d) source: World Bank + dataset: 'World Development Indicators' with access_method=api and documentation_url; (e) the 20 indicators from the Phase 1 list in docs/steps/phase-1-steps.md with our own stable codes (e.g. GDP_USD, GDP_GROWTH, CPI_YOY, POP_TOTAL...), source_concept = the WDI code, English names/definitions from the World Bank metadata API, name_ne left empty for now with a TODO tracked for Phase 3 translation review. Verify each WDI code exists via the API; report any that fail instead of substituting."
2. Run `make seed`. Then run it a second time deliberately — the idempotency habit starts here.
3. Spot-check in Table Editor: indicators table has 20 rows; time_periods has 71; geographies has 1.

**VERIFICATION CHECKLIST:**
- [ ] Row counts: indicators=20 (or fewer with a clear report of any retired codes), time_periods=71, geographies=1, sources=1, datasets=1.
- [ ] Running `make seed` twice produces no duplicates (counts unchanged).
- [ ] Seed files are committed.

**IF IT GOES WRONG:** A WDI code reported missing → ask Claude Code to look up the current replacement code on the World Bank indicator catalog and update the seed with a note. Never let it guess silently.

**COMMIT:** `P1.S6: reference data seeds (geography, periods, units, WDI indicators)`

---

### P1.S7 — The raw data lake

**GOAL (plain language):** Create the vault for untouched original data: a storage bucket plus a small helper that saves every fetched payload with its fingerprint, timestamp, and source URL before anything else happens.

**WHY IT MATTERS:** Blueprint principle 2: raw is immutable, stored BEFORE parsing. The SHA-256 fingerprint later proves a published number traces to an exact original byte-for-byte.

**PREREQUISITES:** P1.S6.
**TIME ESTIMATE:** 45–60 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "In Supabase Storage, we need a private bucket `raw-lake`. Guide me through creating it in the dashboard (or create via API if credentials permit). Then write `ingestion/common/raw_lake.py`: a function that takes (dataset_code, payload bytes, source_url) and stores the payload at a path like `worldbank/wdi/2026-06-11T.../payload.json` together with a sidecar metadata file (sha256, fetched_at UTC, source_url, size). It must never overwrite an existing object. Include a unit test using a temporary/local mode so `make test` doesn't need network. Note: storage API keys go in `.env` only — tell me which variable to add and I will paste the value myself from the Supabase dashboard."
2. Add the storage key to `.env` yourself (same ritual as P1.S2 — never into chat).
3. Have Claude Code run a live smoke test storing a tiny test payload, then show you the object in the Supabase Storage dashboard. Delete the test object afterward via instruction.

**VERIFICATION CHECKLIST:**
- [ ] Bucket `raw-lake` exists and is private.
- [ ] Smoke test object appeared with its metadata sidecar, then was cleaned up.
- [ ] `make test` passes including the new raw-lake test.
- [ ] No storage key appears in any committed file (`git grep` for it returns nothing — ask Claude Code to check).

**IF IT GOES WRONG:** Permission errors → almost always the wrong key type; have Claude Code tell you exactly which key the Supabase dashboard page shows to copy.

**COMMIT:** `P1.S7: raw data lake with hash-verified immutable writes`

---

### P1.S8 — The World Bank ingestion pipeline

**GOAL (plain language):** The first real pipeline: fetch all 20 indicators for Nepal from the World Bank API, save raw, parse, and load into the warehouse under a proper release — rerunnable any time without creating duplicates.

**WHY IT MATTERS:** This step exercises EVERYTHING built so far. Its shape (raw-first → parse → release → load → log) is the template every future pipeline copies.

**PREREQUISITES:** P1.S7.
**TIME ESTIMATE:** 90–120 minutes. The big one — start fresh.

**ACTIONS:**
1. Instruct Claude Code:
   > "Build `ingestion/worldbank/pipeline.py` with `make ingest-wb`, per Master Prompt §3.3: (1) for each indicator in our indicators table with source_concept set, fetch the full Nepal series from the World Bank API v2 (JSON, paginated — handle paging); (2) store each raw response via the raw-lake helper BEFORE parsing; (3) create one `releases` row for this run (dataset=WDI, release_date=today, raw_file_refs=list of stored objects); (4) parse observations: map WDI year→our time_periods, country NP→our geography, value→numeric (skip nulls, count them as rejected with reason 'null value'); (5) insert observations under this release, letting the is_latest mechanics from P1.S5 handle any previous values; (6) write a complete `ingestion_log` row whether the run succeeds or fails; (7) print a plain-language summary: indicators fetched, rows loaded, rows rejected and why. Then add tests with a saved sample API response fixture so parsing is tested offline."
2. Run `make ingest-wb`. Read the summary together.
3. Sanity-check three real numbers: ask Claude Code to query, e.g., Nepal population 2021, GDP growth 2020 (should be negative — COVID), inflation 2022 — and compare them yourself against the World Bank website (data.worldbank.org). Numbers must match.
4. Run `make ingest-wb` a second time. Expected result: a new release row, observation count roughly stable, no duplicate-key errors, previous rows' is_latest flipped appropriately. This is the idempotency + revision model proven in real life.

**VERIFICATION CHECKLIST:**
- [ ] First run: ingestion_log shows success; observations table has data (typically a few hundred to ~1,500 rows depending on series length).
- [ ] Your three spot-checked numbers match the World Bank website.
- [ ] Raw lake contains this run's payloads.
- [ ] Second run completed cleanly: no duplicates, sensible log entry, is_latest correct (Claude Code demonstrates with a query).
- [ ] `make test` green.

**IF IT GOES WRONG:** API hiccups/paging bugs are normal first-pipeline issues — iterate with Claude Code. If numbers don't match the website: STOP, do not proceed; the parse mapping is wrong and finding it now is the entire point of the skeleton.

**COMMIT:** `P1.S8: World Bank WDI ingestion pipeline (raw-first, idempotent, release-tracked)`

---

### P1.S9 — Data-quality gate

**GOAL (plain language):** Teach the pipeline to check its own work: automatic tests that block bad data from being promoted, plus the project's growing test suite.

**WHY IT MATTERS:** Master Prompt §3.3: quality tests run IN the pipeline, not after. This gate is what will later keep a mis-parsed NRB PDF from ever reaching the public.

**PREREQUISITES:** P1.S8.
**TIME ESTIMATE:** 60–90 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Add a quality-gate module the WDI pipeline runs before finalizing a release: (a) percentage-type indicators within plausible bounds (e.g. rates 0–100 where applicable; growth rates within ±50); (b) population strictly positive and within an order-of-magnitude band; (c) every observation resolves to existing indicator/geography/period (FKs guarantee it, but assert anyway and report counts); (d) per-indicator series continuity report — flag gaps of missing years as INFO not failure; (e) no value parsed from a non-numeric source string. Failures mark the run failed in ingestion_log with reasons and do not flip is_latest. Wire into `make ingest-wb`; extend pytest suite; document each rule in a comment with its rationale."
2. Prove the gate works: ask Claude Code to run the pipeline once against a deliberately corrupted local fixture (e.g. literacy = 250%) and show you the run being blocked with a readable reason. Then a normal run to confirm green.

**VERIFICATION CHECKLIST:**
- [ ] Corrupted-fixture run is blocked with a plain-language reason in the log.
- [ ] Normal run passes the gate.
- [ ] `make test` green; test count has grown since P1.S7.

**IF IT GOES WRONG:** Over-strict rules blocking legitimate values (it happens — e.g. growth beyond a bound in a crisis year) → loosen with a comment explaining why; the rules are versioned code, tuned over time.

**COMMIT:** `P1.S9: in-pipeline data-quality gate`

---

### P1.S10 — Minimal public API

**GOAL (plain language):** A small web service on your computer that answers questions like "give me GDP growth for Nepal" with the numbers AND their provenance — the same interface the website, and one day the public, will use.

**WHY IT MATTERS:** Master Prompt §3.5: versioned from day one, provenance in every response. The frontend in P1.S11 consumes exactly this — no shortcuts where the website reads the database directly.

**PREREQUISITES:** P1.S9.
**TIME ESTIMATE:** 60–90 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Create the FastAPI app in `api/` per Master Prompt §3.5: `GET /v1/indicators` (list with codes, names, units, topics), `GET /v1/indicators/{code}`, and `GET /v1/data?indicator=CODE&geo=NP` returning is_latest observations ordered by period, each response wrapped with provenance: source name, dataset, release date, license, unit, footnotes. Pydantic models throughout; readable JSON; `make api` to run locally; basic tests with FastAPI's test client. Read-only — no write endpoints exist at all."
2. Run `make api`. Open `http://localhost:8000/docs` in your browser — FastAPI auto-generates interactive documentation. Click around; this page alone is something many real portals lack.
3. In the docs page, execute `/v1/data?indicator=GDP_GROWTH&geo=NP` yourself and read the JSON: values, years, and a provenance block naming the World Bank.

**VERIFICATION CHECKLIST:**
- [ ] `/docs` opens and lists the three endpoints.
- [ ] Your GDP_GROWTH query returns data with the provenance block.
- [ ] An unknown indicator code returns a clean, explanatory error (not a crash).
- [ ] `make test` green.

**IF IT GOES WRONG:** Port already in use → ask Claude Code to use another port. Empty responses → check is_latest filtering with Claude Code; the data is there from P1.S8.

**COMMIT:** `P1.S10: minimal versioned read API with provenance`

---

### P1.S11 — First chart in the browser

**GOAL (plain language):** A simple local web page: pick an indicator from a dropdown, see an interactive chart — hover for exact values, source cited beneath. The portal's first heartbeat.

**WHY IT MATTERS:** Completes the slice through every layer. Deliberately minimal in looks: the real design system is a Phase 3 step done properly (Master Prompt §3.6) — today we prove the plumbing, not the paint.

**PREREQUISITES:** P1.S10.
**TIME ESTIMATE:** 90–120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Create the Next.js app in `web/` consuming the local API (never the database directly): one page with an indicator dropdown (from /v1/indicators, grouped by topic) and an ECharts line chart of the selected series with hover tooltips showing year and exact value with the unit, a loading state, an error state per Master Prompt §3.6 ('what happened + offer the data as a table'), and beneath the chart the attribution line built from the provenance block: 'Source: World Bank — World Development Indicators, release {date}' linking to the source. Mobile-responsive at a basic level. `make web` to run. Keep styling minimal and clean — the design system comes in Phase 3."
2. Run `make api` and `make web`; open the page in your browser.
3. The moment: select "GDP growth (annual %)". You should see Nepal's economic story — including the 2020 dip — drawn from data that traveled source → raw lake → warehouse → API → screen, every hop verifiable.
4. Try it on your phone via your computer's local address (Claude Code will tell you how) — a preview of the mobile-first requirement.

**VERIFICATION CHECKLIST:**
- [ ] Dropdown lists all seeded indicators by topic.
- [ ] Chart renders for at least 5 different indicators; hover shows exact values with units.
- [ ] Source attribution with release date appears under every chart.
- [ ] Stopping the API (`Ctrl+C`) makes the page show the designed error state, not a blank crash.

**IF IT GOES WRONG:** CORS errors (browser blocking the page from calling the API) are the classic issue — Claude Code fixes this in the API config in minutes.

**COMMIT:** `P1.S11: first interactive, source-attributed chart`

---

### P1.S12 — Phase close: prove it, document it, log it

**GOAL (plain language):** Verify the whole skeleton holds together, prove the project can be rebuilt from scratch, and formally close the phase.

**WHY IT MATTERS:** Master Prompt §3.1's "README test" and §7's quality bar items get their first real measurement here. A phase isn't done because the last step worked — it's done when the whole is verified.

**PREREQUISITES:** P1.S1–S11.
**TIME ESTIMATE:** 60 minutes.

**ACTIONS:**
1. The rebuild drill — instruct Claude Code:
   > "Following ONLY the README, as if you had never seen this project: from a fresh clone simulation, run setup → migrate → seed → ingest-wb → api → web, and report every place the README was unclear or wrong. Fix the README accordingly."
2. The traceability drill (Quality Bar item 1) — instruct:
   > "Pick one number visible in the chart — Nepal GDP growth 2020 — and show me its full chain: the chart value → the API response → the observations row → its release → the raw-lake object and its source URL. Time how long the trace takes."
3. Phase exit checklist below; then the log entry and a final commit. Note in PROJECT_LOG anything Phase 1 taught us that should shape Phase 2's step file (there will be something — there always is).

**VERIFICATION CHECKLIST (= PHASE 1 EXIT CRITERIA):**
- [ ] Fresh-start drill completes from README alone.
- [ ] Traceability drill: chart → raw source completed, and in under a minute.
- [ ] `make test` and `make lint` green.
- [ ] All Phase 1 commits pushed to GitHub; `make migrate-status` shows 0001–0003 applied.
- [ ] You, personally, can demo the portal to a friend in 2 minutes and answer "where does this number come from?"
- [ ] PROJECT_LOG.md closes the phase with lessons-for-Phase-2 noted.

**IF IT GOES WRONG:** Anything failing here is a gift — it failed in a 20-indicator skeleton instead of a 2,000-indicator portal. Fix forward, re-run the drill.

**COMMIT:** `P1.S12: phase 1 closed — walking skeleton verified end to end`

---

## After Phase 1

Say to Claude (in the Claude Project, with the PROJECT_LOG lessons at hand): **"Phase 1 exit criteria met — generate the Phase 2 step file."** Phase 2 is where the project becomes unmistakably *Nepali*: the BS↔AD calendar bridge, the old/new geography crosswalk, NRB's Excel files with the staging-and-review workflow, and Census 2021 — designed around whatever Phase 1 taught us.
