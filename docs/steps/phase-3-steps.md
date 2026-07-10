# PHASE 3 — THE PUBLIC PORTAL — Step File

**Version 0.9 — DRAFT, July 2026**
**Governed by: Master Prompt v1.0 · Architecture Blueprint v1.0**
**Assumes: Phase 2 exit criteria fully met (NRB + World Bank inflation aligned on one axis, review gate proven — see docs/steps/phase-2-steps.md and the P2.S14 log entry).**

> **DRAFT STATUS:** The Master Prompt (§4) requires step files to be finalized only when the previous phase nears completion, so later steps incorporate what earlier phases taught. This draft was written mid-Phase-2 at the founder's request. **Before starting P3.S1: re-read the P2.S14 PROJECT_LOG lessons, fill in the carry-forward section below, adjust any step this invalidates, and bump this file to Version 1.0.**

**Phase goal: turn the proven engine into a *public product*. Build the design system, the information architecture, the interactive chart framework, choropleth maps with drill-down, downloads, public API documentation, and the bilingual UI — then deploy it softly and prove it on a real stranger.**

**Why now:** Phases 1–2 proved the hard invisible things: the universal model, two calendars on one axis, two geographies, revisions, the review gate. None of that matters if a journalist in Surkhet can't find a number, understand it, chart it, and cite it in under a minute on a phone. Phase 3 is where trustworthiness becomes *visible*.

**Total founder time: ~16–22 hours across 14 steps. One step per session. Never two.**
**Phase exit criterion: a stranger — someone who has never seen the project — can find, understand, chart, and download a statistic without help, on the deployed site, tested on a real stranger. And the P3.S14 checklist passes.**

**How to run every session:** open Claude Code in the project folder, open this file, and tell Claude Code: "We are on step P3.SX of docs/steps/phase-3-steps.md. Follow it under the master prompt." Approve actions one at a time; verify with the checklist; commit; log.

---

## Carry-forward lessons from Phase 2 (apply in every step)

**TO BE FILLED AT P2.S14 CLOSE from the PROJECT_LOG "lessons for Phase 3" entry.** Expected candidates (verify against the actual log; delete what didn't happen, add what did):

1. *(placeholder)* UTF-8 stdout helper (`ingestion/common/io_utf8.py`) is mandatory in every entrypoint script — Phase 3 build scripts included.
2. *(placeholder)* The Playwright smoke-test pattern from P2.S13 is the template for every new page: no page ships without a rendering assertion.
3. *(placeholder)* The "estimated via boundary mapping" flag contract (P2.S6) — the frontend must display it wherever crosswalked data appears; maps in P3.S8 depend on it.
4. *(placeholder)* Supabase free tier auto-pauses when idle; budget a "restore project from dashboard" check at the start of each session.
5. *(placeholder — add real lessons from PROJECT_LOG here)*

**Binding from the Master Prompt for this phase:** branch workflow becomes mandatory now (§3.1: "switch to branches no later than Phase 3") — every step from P3.S1 onward is built on `step/P3-SX-short-name` and merged after verification.

---

### P3.S1 — Branch workflow + the design system foundations

**GOAL (plain language):** Before any page is built, define the portal's visual language once, in code — colors, type sizes, spacing, a color-blind-safe chart palette, and the reusable building blocks (cards, stat tiles, chart frame, data table, footnote block) — so every later page assembles from the same parts and nothing is styled ad hoc. Also switch the repo to the branch-per-step workflow, which is mandatory from this phase.

**WHY IT MATTERS:** Master Prompt §3.6: "Design system first (Phase 3 opening step)… No ad-hoc styling." Consistency is a trust signal for a statistics portal: if every chart frame and footnote looks the same, readers learn the visual grammar once.

**PREREQUISITES:** Phase 2 complete; this file bumped to v1.0 with real carry-forward lessons.
**TIME ESTIMATE:** 90–120 minutes.

**ACTIONS:**
1. Adopt branches. Instruct Claude Code:
   > "From now on every step starts with `git checkout -b step/P3-SX-short-name` from an up-to-date `main` and ends with a merge after verification. Document this in README's contributing section. Create the branch for this step now."
2. The design tokens. Instruct:
   > "In `web/`, create a token layer (CSS variables or the framework's token mechanism): color tokens (background/surface/text/accent, semantic success/warning/error), a type scale, a spacing scale, and a categorical chart palette that is color-blind-safe (verify pairwise distinguishability for deuteranopia; document the check). Tokens must work in both a light and dark theme even if only light ships now. No component may use a raw hex value — lint or grep-check for violations."
3. The base components. Instruct:
   > "Build the reusable components using only tokens: Card, StatTile (headline number + label + optional sparkline), ChartFrame (title, chart slot, source-citation footer that is REQUIRED — the component refuses to render without a source prop), DataTable, FootnoteBlock. Add a `/design` dev-only page rendering every component with sample data (English and Devanagari samples), plus designed empty/loading/error states for each."
4. Open `/design` and eyeball every component in both languages.

**VERIFICATION CHECKLIST:**
- [ ] `/design` page shows all components, with Devanagari rendering correctly.
- [ ] ChartFrame cannot render without a source citation (deliberate omission fails loudly in dev).
- [ ] No raw hex colors outside the token file (grep proves it).
- [ ] Work merged from `step/P3-S1-…` branch; `main` still green (`make test`, Playwright smoke).

**IF IT GOES WRONG:** Token systems sprawl — if you find yourself defining more than ~25 tokens, stop and cut back; a small system that is actually reused beats a large one that isn't.

**COMMIT:** `P3.S1: design system tokens + base components (+ branch workflow adopted)`

---

### P3.S2 — Information architecture and routing skeleton

**GOAL (plain language):** Lay out the site's skeleton — home, topic pages, indicator pages, geography profiles, search, and an about/data-sources page — as real routes with designed placeholder content, so navigation exists before any page is deep.

**WHY IT MATTERS:** Master Prompt §5 P3: information architecture precedes features. A stranger's first act is navigation; if the skeleton is right, every later step just fills a slot.

**PREREQUISITES:** P3.S1.
**TIME ESTIMATE:** 60–90 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Create the route skeleton in `web/`: `/` (home), `/topics/[topic]` (the Blueprint §4.2 topic list: population, economy, labor, health, education, agriculture, environment, governance), `/indicators/[code]`, `/geo/[code]`, `/search`, `/about` (mission + data sources + licensing), `/api-docs` (placeholder). Each route uses the layout shell (header with nav + language toggle placeholder, footer with attribution) and the designed empty state from P3.S1 — no default-framework placeholder text anywhere. Static-generate what can be static."
2. Click through every route; confirm the shell, nav, and empty states.

**VERIFICATION CHECKLIST:**
- [ ] All routes render inside one consistent shell; no unstyled or default placeholder pages.
- [ ] Topic list matches the Blueprint §4.2 topics exactly.
- [ ] Playwright smoke extended to assert each route renders.

**IF IT GOES WRONG:** Scope creep into real content — resist; this step is only the skeleton. Content arrives in S4–S9.

**COMMIT:** `P3.S2: information architecture + routing skeleton`

---

### P3.S3 — The bilingual layer (i18n)

**GOAL (plain language):** Route every piece of UI text through a translation layer with an English/Nepali toggle, and wire data-driven names (indicators, places) to the `name_en`/`name_ne` fields the schema has carried since day one.

**WHY IT MATTERS:** Blueprint principle 7: bilingual by design, not bolted on. Doing this *before* the deep pages means no page is ever built monolingual and retrofitted.

**PREREQUISITES:** P3.S2.
**TIME ESTIMATE:** 90–120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Add an i18n layer to `web/` (the framework-standard approach): every UI string lives in `en`/`ne` message files, a visible language toggle in the header persists the choice, and data names render from name_en/name_ne based on locale with fallback to English when name_ne is empty (fallback must be visible in a dev report, not silent — list untranslated keys). Numerals stay English at launch (per §3.6); leave a documented hook for Devanagari numerals later. The API already returns both name fields — verify, and extend if any endpoint dropped name_ne."
2. Toggle to Nepali and walk the skeleton: header, nav, topic names, one indicator name in Devanagari.

**VERIFICATION CHECKLIST:**
- [ ] Language toggle switches all UI chrome; choice persists across pages.
- [ ] An indicator and a geography display their `name_ne` in Nepali mode (real Devanagari from the DB, not a translation file).
- [ ] `make web-i18n-report` (or equivalent) lists missing translations; nothing hard-codes English in components.

**IF IT GOES WRONG:** Devanagari font fallback looks broken → ship a proper webfont subset rather than relying on system fonts; check on Windows and Android.

**COMMIT:** `P3.S3: bilingual UI layer (en/ne) wired to schema name fields`

---

### P3.S4 — The indicator page: density with hierarchy

**GOAL (plain language):** Build the real indicator page — the portal's most important page — leading with the headline number and sparkline, then the interactive chart, then the breakdowns table, then full metadata (definition, unit, source, license, revision note), in that order.

**WHY IT MATTERS:** Master Prompt §3.6, "the Bloomberg lesson": the answer in 3 seconds, the depth in 3 minutes. This page is what a journalist screenshots and what a researcher cites.

**PREREQUISITES:** P3.S3.
**TIME ESTIMATE:** 120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Build `/indicators/[code]` for real: StatTile with the latest value + period + a small sparkline of the series; below it the ChartFrame with the full interactive series (chart interactivity itself deepens next step — a basic line with tooltip is enough here); below that a DataTable of observations (period, value, unit, status, source) that doubles as the chart's accessible alternative; below that the metadata block from the catalog: definition_en/ne, unit, topic, source + dataset + license with links, and a revision note when any observation in view has superseded history. Static-generate these pages from the indicator list where possible; data lazy-loads. Every element cites through the ChartFrame source contract."
2. Open two indicators — one World Bank, one NRB (fiscal-year) — and check the hierarchy top to bottom in both languages.

**VERIFICATION CHECKLIST:**
- [ ] Headline value + sparkline visible without scrolling on a phone-sized viewport.
- [ ] Fiscal-year NRB series shows correct BS/fiscal labels; no off-by-one against P2.S13's aligned axis rules.
- [ ] The data table contains exactly the charted values (spot-check three), with unit and source columns.
- [ ] Metadata shows definition, license, and links to the original source.

**IF IT GOES WRONG:** Page feels slow → check that observation data lazy-loads and pages are static-generated; the metadata catalog read must not block first paint.

**COMMIT:** `P3.S4: indicator page — headline, chart, table, metadata hierarchy`

---

### P3.S5 — The interactive chart framework (§3.6 in full)

**GOAL (plain language):** Upgrade the chart to the full interactivity standard: hover tooltips with exact values, period-range selection, add-a-geography comparison series, linear/log toggle where meaningful, PNG export, and a "data behind this chart" CSV button — every chart, always citing its source.

**WHY IT MATTERS:** Master Prompt §3.6 defines this exact list as the interactivity standard. Built once as a framework around ECharts, every future chart inherits it for free.

**PREREQUISITES:** P3.S4.
**TIME ESTIMATE:** 120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Extend ChartFrame into the full chart framework on ECharts: (a) tooltips showing exact value, unit, period label (BS label too for fiscal periods), and source per series; (b) a period-range selector; (c) 'compare' control that adds another geography of the same indicator as a series (API already supports multi-series from P2.S13 — extend if needed); (d) linear/log toggle, shown only when all values are positive; (e) PNG export that INCLUDES the title and source citation in the exported image; (f) a CSV button that downloads exactly the charted data with a provenance header row. Series colors come from the P3.S1 palette in order. Update the Playwright test to exercise tooltip, compare, and CSV download."
2. Play with it: compare two provinces on a census indicator, export the PNG, open the CSV.

**VERIFICATION CHECKLIST:**
- [ ] All six §3.6 interactions work on the indicator page.
- [ ] Exported PNG carries the source citation (screenshot-safe attribution — the Quality Bar's journalist test).
- [ ] Downloaded CSV matches the chart's data and includes source/license header lines.
- [ ] Playwright covers tooltip, comparison, and CSV; `make web-test` green.

**IF IT GOES WRONG:** Log toggle on data with zeros/negatives → the toggle must hide itself, not error; that's why (d) is conditional.

**COMMIT:** `P3.S5: full interactive chart framework (tooltips, compare, export, CSV)`

---

### P3.S6 — Search that speaks both languages

**GOAL (plain language):** Build search over indicators and geographies so a user can type "literacy", "साक्षरता", or a district's name in any common spelling and land on the right page.

**WHY IT MATTERS:** A stranger's path usually starts at a search box. The `geo_aliases` table (P2.S6) was built precisely so spelling variants resolve without guessing — search is its public payoff.

**PREREQUISITES:** P3.S5.
**TIME ESTIMATE:** 90–120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Add `/v1/search?q=` to the API: match against indicator name_en/name_ne/code and geography name_en/name_ne plus geo_aliases, using PostgreSQL full-text/trigram matching (justify the index in the migration comment). Return typed results (indicator vs geography) with both names. In `web/`, wire `/search` and a header search box with debounced suggestions; results are grouped by type and respect the current language. Empty and no-results states designed. Log unmatched queries (privacy-safe: query text only, no user data) — they become future alias seeds."
2. Test the three spellings above plus a misspelling ("Kathamandu") and one Devanagari query.

**VERIFICATION CHECKLIST:**
- [ ] English, Devanagari, and alias-variant queries all reach the right page.
- [ ] A reasonable misspelling still finds the target (trigram similarity), an unreasonable one gets the designed no-results state.
- [ ] Search endpoint is read-only, cached, and rate-limited like the rest of `/v1/`.

**IF IT GOES WRONG:** Devanagari matching behaves oddly → check the text-search configuration; simple/trigram usually beats language-stemmer configs for Nepali. Never "fix" by transliterating silently.

**COMMIT:** `P3.S6: bilingual search over indicators, geographies, and aliases`

---

### P3.S7 — Boundaries in, first choropleth map

**GOAL (plain language):** Load Nepal's official boundary files (GeoJSON for provinces and districts) with provenance, link them to our geography rows, and render the first choropleth — a province map shaded by a census indicator.

**WHY IT MATTERS:** Blueprint §6: openly-licensed official boundaries stored in the repo with provenance notes; `geographies.geometry_ref` has waited since P1 for this. Maps are how most people *recognize* data about Nepal.

**PREREQUISITES:** P3.S6.
**TIME ESTIMATE:** 120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Acquire openly-licensed official GeoJSON for the 7 provinces and 77 districts (Survey Department or a recognized open redistribution). Store under `reference/geojson/` with a provenance note (URL, retrieval date, license) — Prime Directive 7: if licensing is unclear, stop and report, don't ship. Simplify geometries for web size (document the tolerance), key each feature to our geography `code`, and populate `geometry_ref`. Verify every feature matches exactly one geography row and report orphans on both sides rather than dropping them. Then render an ECharts choropleth of a census indicator by province inside ChartFrame — hover shows name (current language) + value + unit, and the map cites its source AND the boundary provenance."
2. Compare the map's values against the same indicator's data table for two provinces.

**VERIFICATION CHECKLIST:**
- [ ] GeoJSON in `reference/geojson/` with license + provenance note; every feature ↔ geography match verified (7/7, 77/77).
- [ ] Province choropleth renders with correct values (two spot-checks against the table), bilingual hover, dual citation (data source + boundaries).
- [ ] Map file size is web-reasonable (simplified geometry documented).

**IF IT GOES WRONG:** A feature-to-geography mismatch (spelling/code) → resolve via `geo_aliases`, never by editing the GeoJSON's data by hand; the boundary file is raw-ish reference data.

**COMMIT:** `P3.S7: official boundaries + first province choropleth`

---

### P3.S8 — Map drill-down and the boundary-vintage flag

**GOAL (plain language):** Make maps navigable — click a province to see its districts (local units when data exists) — and make the "estimated via boundary mapping" flag appear whenever a map shows crosswalked (pre-2015) data on current boundaries.

**WHY IT MATTERS:** Master Prompt §3.6: province → district → local-unit drill-down with the Blueprint §5.2 vintage flag. This is the honesty mechanism for the 2015 break, now user-facing.

**PREREQUISITES:** P3.S7.
**TIME ESTIMATE:** 90–120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Add drill-down to the choropleth: clicking a province re-renders the map to its districts (and to local units where a dataset has that level), with a breadcrumb to navigate back up. When the displayed series involves crosswalked data (the P2.S6 flag contract), render the 'estimated via boundary mapping' badge on the ChartFrame and mark affected areas' tooltips. Extend Playwright: drill into one province and assert the district map and breadcrumb render."
2. Drill Bagmati → districts; then display a pre-2015 series (Census 2011 era, if present via crosswalk) and confirm the flag appears.

**VERIFICATION CHECKLIST:**
- [ ] Province click → district map with correct district values; breadcrumb returns to the national view.
- [ ] Crosswalked data shows the vintage flag on the frame and in tooltips; native-boundary data shows no flag.
- [ ] Playwright drill-down assertion green.

**IF IT GOES WRONG:** No crosswalked series exists to test the flag → test the contract with a deliberately-flagged dev fixture rather than skipping; the flag path must be exercised before Phase 3 ends.

**COMMIT:** `P3.S8: map drill-down + boundary-vintage flag surfaced`

---

### P3.S9 — Geography profile pages

**GOAL (plain language):** Give every place its own page — a province or district profile leading with headline stats (population, literacy, households…), a mini-map locating it, and the list of indicators available for it.

**WHY IT MATTERS:** Half of real questions are place-first ("tell me about Karnali"), not indicator-first. The IA (P3.S2) reserved `/geo/[code]` for exactly this.

**PREREQUISITES:** P3.S8.
**TIME ESTIMATE:** 90–120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Build `/geo/[code]`: header with name_en/name_ne + level + parent breadcrumb (district → province → Nepal); a StatTile row of headline indicators available for this geography (census population, literacy, households — driven by data availability, not hard-coded); a locator mini-map (this area highlighted); and an 'available indicators' list linking into indicator pages pre-filtered to this geography. Static-generate profiles for provinces and districts. Bilingual throughout. Empty states for places with little data are designed, honest, and suggest the parent geography."
2. Open one province and one district profile in both languages.

**VERIFICATION CHECKLIST:**
- [ ] Profile shows correct headline values (spot-check against the indicator page) with sources.
- [ ] Breadcrumb chain and mini-map are correct for both samples.
- [ ] A data-sparse local unit shows the designed honest empty state, not a broken page.

**IF IT GOES WRONG:** Hard-coding "headline indicators" per place → drive from an availability query + a small curated priority list in code, or profiles rot as data grows.

**COMMIT:** `P3.S9: geography profile pages (place-first navigation)`

---

### P3.S10 — Downloads: CSV and Excel, with attribution built in

**GOAL (plain language):** Let users take the data home: CSV and Excel download for any indicator/geography/period selection — from chart buttons and from a documented `/v1/data.csv` endpoint — with source, license, and retrieval date embedded in every file.

**WHY IT MATTERS:** Blueprint vision: downloads are a first-class output. Master Prompt §3.5 names `/v1/data.csv`. An undocumented number in a spreadsheet is how attribution dies — so the file itself carries its provenance.

**PREREQUISITES:** P3.S9.
**TIME ESTIMATE:** 90 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Implement `/v1/data.csv` (same query params as `/v1/data`) streaming CSV with a provenance header block (# source, dataset, license, definition, unit, retrieved-at, portal URL) above the column header; and an Excel variant (openpyxl) with a separate 'About this data' sheet holding the same provenance plus the indicator definition in both languages. Wire the chart CSV button (P3.S5) and add an Excel option. Content-Disposition filenames are meaningful (indicator_geo_period). Both endpoints cached and rate-limited like the rest of /v1/. Add tests asserting the provenance block exists and values match the JSON endpoint."
2. Download both formats for one NRB series; open them and read the provenance with your own eyes.

**VERIFICATION CHECKLIST:**
- [ ] CSV and Excel downloads carry the provenance block/sheet; values match `/v1/data` exactly (test proves it).
- [ ] Fiscal-year periods are labeled with both BS and Gregorian labels in the files.
- [ ] Endpoints documented in the API's auto-docs.

**IF IT GOES WRONG:** Excel mangles Devanagari or dates → set explicit cell types and UTF-8 throughout; verify in actual Excel/LibreOffice, not just by re-parsing in Python.

**COMMIT:** `P3.S10: CSV/Excel downloads with embedded provenance`

---

### P3.S11 — The public API documentation page

**GOAL (plain language):** Turn the API from "exists" to "usable by strangers": a human-friendly docs page with live examples, the versioning promise, rate limits, licensing/attribution rules, and copy-paste snippets.

**WHY IT MATTERS:** Master Prompt §3.5: the API is a public product with a contract ("breaking changes → /v2/, never silent edits"). Researchers and civic hackers are a launch audience; their first impression is this page.

**PREREQUISITES:** P3.S10.
**TIME ESTIMATE:** 60–90 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Build `/api-docs` in the portal (human-oriented, bilingual chrome; endpoint reference can stay English): what the API is, the base URL, every /v1/ endpoint with a live 'try it' example against real data, the versioning promise quoted from the master prompt, rate limits, cache behavior, the provenance-in-every-response guarantee with an annotated example response, and the attribution requirement with a ready-to-copy citation line. Link the FastAPI auto-docs for the full schema. Add copy-paste snippets (curl, Python, JavaScript) that actually run."
2. Run each snippet yourself from a terminal outside the repo.

**VERIFICATION CHECKLIST:**
- [ ] Every documented example returns real data when copy-pasted.
- [ ] Versioning promise, rate limits, and attribution requirement stated plainly.
- [ ] Page linked from the site footer and `/about`.

**IF IT GOES WRONG:** An example exposes an endpoint inconsistency (naming, missing provenance field) → fix the API additively now, before public eyes; this step is the API's dress rehearsal.

**COMMIT:** `P3.S11: public API documentation with live examples`

---

### P3.S12 — Performance, accessibility, SEO, and social cards

**GOAL (plain language):** Make the portal fast on a cheap phone, usable by everyone, and shareable: hit the performance budget (LCP < 2.5 s on mid-range Android/3G), pass WCAG 2.1 AA basics, and add SEO metadata + social-share cards so a shared indicator link previews with its headline number.

**WHY IT MATTERS:** Master Prompt §3.6 budgets and accessibility are requirements, not aspirations — "a journalist on a phone in Surkhet gets a chart in under 3 seconds." Shares and search are how strangers arrive.

**PREREQUISITES:** P3.S11.
**TIME ESTIMATE:** 120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Run Lighthouse (mobile, throttled) against home, one indicator page, one map page, one profile. Report the numbers honestly, then fix to budget: static generation coverage, lazy-loaded chart data, font subsetting (Devanagari webfont is the usual heavy item), image/bundle trimming. Then accessibility: keyboard-navigate every interactive element (charts fall back to their data tables — §3.6 says the table IS the alternative), label controls, check contrast with the token palette, add skip-links. Then SEO: titles/descriptions per page from real metadata, sitemap, structured data for indicators (Dataset schema.org), and social cards (OG/Twitter) rendering the indicator's headline number + sparkline image. Playwright asserts meta tags on indicator pages."
2. Re-run Lighthouse; record before/after in the log. Tab through an indicator page with the keyboard only.

**VERIFICATION CHECKLIST:**
- [ ] LCP < 2.5 s (throttled mobile) on the four audited pages; numbers logged before/after.
- [ ] Full keyboard path: search → indicator → range-select → download, no mouse.
- [ ] Contrast passes AA with the token palette (fix tokens, not instances, if not).
- [ ] A pasted indicator link previews with title, description, and card image.

**IF IT GOES WRONG:** Budget misses trace overwhelmingly to fonts and chart-library payload — subset the font, load ECharts only where charts exist. Don't disable features to pass; make them lazy.

**COMMIT:** `P3.S12: performance budget, WCAG AA pass, SEO + social cards`

---

### P3.S13 — Soft deployment: the portal goes live (quietly)

**GOAL (plain language):** Deploy the real portal and API to production hosting — building on the existing Render blueprint if it still fits — with production environment variables, caching headers doing their job, error monitoring, and a deploy-on-merge pipeline. Live, but not yet announced.

**WHY IT MATTERS:** Master Prompt §5 P3 ends with soft deployment: the stranger test (next step) must run on the real deployed thing, not localhost. Caching (§3.5) only proves itself with a CDN in front.

**PREREQUISITES:** P3.S12.
**TIME ESTIMATE:** 90–120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Review the existing deploy setup (the Render blueprint from the Phase 2 era) against Phase 3's needs; keep or revise it deliberately, and document the decision in docs/decisions/. Production deploy of API + web with: production env vars from the host's secret store (never in the repo — verify .env.example is complete and current), Cache-Control/ETag verified live (show response headers proving a cached hit), a custom domain if the founder has one (decision needed), error monitoring wired (host-native or simple), and CI deploy-on-merge to main with the test suite as a gate. Update docs/runbooks/ with a deploy + rollback runbook."
2. Founder decision: domain name now or later.
3. Open the live URL on your phone (real mobile network, not wifi). Run the P3.S11 API snippets against the live API.

**VERIFICATION CHECKLIST:**
- [ ] Live URL serves the portal; live API responds with correct cache headers (a repeated request is a cache hit — proven by headers/timing).
- [ ] A test failure on a branch blocks deploy (prove it once with a deliberate failing commit on a branch, then revert).
- [ ] Rollback runbook exists and names the exact commands/clicks.
- [ ] No secret anywhere in the repo; production DB role is least-privilege per §3.8.

**IF IT GOES WRONG:** Free-tier services sleep (see the Supabase lesson) → document the wake behavior in the runbook and decide (founder call) whether launch requires a paid tier; don't discover this during the public launch.

**COMMIT:** `P3.S13: soft production deployment with CI gate + rollback runbook`

---

### P3.S14 — The stranger test + phase close

**GOAL (plain language):** Put a real person who has never seen the project in front of the live portal, ask them to find, understand, chart, and download a statistic — watch silently, fix what tripped them — then run the phase drills, update docs, and close Phase 3.

**WHY IT MATTERS:** The phase exit criterion is behavioral, not technical: "a stranger can find, understand, chart, and download a statistic without help — tested on a real stranger." No checklist substitutes for watching one.

**PREREQUISITES:** P3.S1–S13; one recruited stranger (friend/family member who hasn't seen the project).
**TIME ESTIMATE:** 90–120 minutes (including the session with the stranger).

**ACTIONS:**
1. Run the stranger session: give them the live URL and three tasks — "find Nepal's inflation and tell me what it was last year", "find your home district's population", "download the data behind either one." Watch silently; take notes; do not help unless fully stuck (a full stuck = a failed check).
2. Instruct Claude Code with your notes:
   > "Here is what the stranger struggled with: [notes]. Triage: fix the quick UX issues now on a branch; file the rest as logged follow-ups (no silent TODOs — Master Prompt §3.7.5)."
3. Drills — instruct:
   > "README fresh-clone drill including the web build and deploy docs; traceability drill on the live site (public chart → API → warehouse → release → raw file → source URL, under a minute); full test suite + dbt tests + Playwright against the deployed URL."
4. PROJECT_LOG entry closing the phase, with lessons for Phase 4; **generate/finalize the Phase 4 step file from its draft, incorporating those lessons**; final commit.

**VERIFICATION CHECKLIST (= PHASE 3 EXIT CRITERIA):**
- [ ] The stranger completed all three tasks unaided (or the blockers found are fixed and re-tested on a second stranger/session).
- [ ] Live traceability drill: public chart to source URL in under a minute.
- [ ] `make test`, `make dbt-test`, Playwright (against production), Lighthouse budget: all green on the deployed site.
- [ ] README drill passes including deployment; all Phase 3 work merged and pushed.
- [ ] Both languages verified on the live site by a native reader (the founder counts).
- [ ] PROJECT_LOG closes the phase with lessons-for-Phase-4; the Phase 4 step file is finalized to v1.0.

**IF IT GOES WRONG:** The stranger fails a task → that IS the result; the phase stays open until the fix is verified with a fresh stranger session. Do not rationalize a failed stranger test.

**COMMIT:** `P3.S14: phase 3 closed — public portal verified on a real stranger`

---

## After Phase 3

Say to Claude (with the PROJECT_LOG lessons at hand): **"Phase 3 exit criteria met — finalize the Phase 4 step file."** Phase 4 is *Industrial Strength*: Dagster orchestration and schedules, monitoring and freshness alerts, expanded dbt coverage, the IMF and ILO pipelines, the ministry PDF workflow with a review UI, the performance/caching pass against the §3.5 budgets, the restore drill, and a load test — turning a hand-run portal into a system that runs itself and tells you when it's unwell.
