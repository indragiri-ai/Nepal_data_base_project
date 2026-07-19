# PHASE 2B — FULL-DEPTH DATA + SECTOR PORTAL — Step File

**Version 1.0 — July 2026 (authored with Fable 5; judgment front-loaded so any
capable model can implement mechanically)**
**Governed by: Master Prompt v1.0 · Architecture Blueprint v1.0 · Decision 0003
(sectors organize the portal; sources are provenance only).**

**Phase goal: take the portal from "impressive sliver" to "genuinely deep" —
the full World Bank catalog for Nepal, every census topic, NRB beyond the
aggregates — and reorganize the frontend by SECTOR (not source), with a
distinctive landing page and the officially correct map of Nepal. These steps
come BEFORE further Phase 3 work.**

**Founder decisions already made (do not re-ask):** sector list as defined in
P2B.S5; sector pages are DASHBOARD style (curated charts on top, full list
below); landing page pursues the "data orbit" concept (P2B.S6); implementing
model works autonomously per the founder's standing working style — execute the
whole step, self-verify against the checklist, and present results; the founder
eyeballs at the end. Stop only where a step explicitly says STOP.

**How to run every session:** open Claude Code in the project folder and say:
"We are on step P2B.SX of docs/steps/phase-2b-expansion-steps.md. Follow it
under the master prompt." One step per session unless a step says it can be
batched.

---

## Reconciliation with existing step files (read once)

- **P2.S11 (census headline tables) is SUPERSEDED** — implemented 2026-07-19 the
  API way (see PROJECT_LOG): NSO census API discovered, 7+77 geographies seeded
  with P-codes, 765 observations live, /population choropleth shipped. P2B.S7–S8
  extend that work; do not redo P2.S11 as written (no staging gate needed for
  the clean JSON API — rule 3 allows direct load for clean APIs).
- **P2.S4 (new geography) is DONE** for provinces+districts (P-codes, Devanagari,
  parent chains — see `reference/census/PROVENANCE.md`). Local units (753) are
  seeded in **P2B.S8**, not before. P2.S5–S6 (old geography, crosswalk) remain
  DEFERRED by founder decision until a dataset needs them.
- **P2.S7–S10 (NRB CPI onboarding)** remain valid and are NOT replaced by this
  file; they can run before or after P2B — but P2B.S2 (automation) should exist
  before any new recurring source.
- **P3.S1 (design system) is partially DONE** (2026-07-18 visual pass:
  tokens, header/footer, chart theme, validated palette). **P3.S2 (IA/routing)
  is ABSORBED by P2B.S5** — when Phase 3 resumes, treat P3.S2 as done and
  re-verify its checklist against the sector IA.
- The **Playwright smoke test** (P2 lesson 5) is folded into P2B.S5's checklist
  — sector pages + map get automated render checks at last.

## Facts bank (verified 2026-07-18/19 — cite, don't re-derive)

- Census API base: `https://censusapi.cbs.gov.np/api/v1`; filters
  `?province=&district=&municipality=`; response envelope
  `{status, code, success, data}`. District ids 1–77 & province ids 1–7 mapped
  to our P-codes in `reference/census/nso_geo_ids.csv`; municipality ids are
  embedded in the site's JS (pattern
  `{district:"<id>",value:"<mun-id>",label:"<name>",no_of_wards:N}` — e.g.
  Kathmandu Metropolitan City = district 28, value 8).
- Known-good spot-check values: national pop 29,164,578; Kathmandu district
  2,041,587; sex ratio 95.59; density 198; growth 0.92; literacy 76.2
  (M 83.6 / F 69.4); religion hindu 81.2%; the 7 provinces SUM EXACTLY to the
  national total.
- WB API: enumerate WDI indicators via
  `https://api.worldbank.org/v2/source/2/indicator?format=json&per_page=1000`
  (source 2 = WDI; ~1,400–1,500 rows, paged). Nepal series:
  `/v2/country/NPL/indicator/{code}`. License CC BY 4.0. Metadata gives
  name/definition/topics but NOT a structured unit — see P2B.S3 unit rules.
- Existing machinery to REUSE, never reinvent: `RawLake`, `run_quality_gate`,
  change-aware loading keyed (indicator, geo, period, breakdowns), seed
  upserts on natural keys, `ingestion/nso/census_layout.py` parser style
  (registry + fail-loudly), `/v1/data/geo` for choropleths, `EChart`/
  `ChoroplethMap` modular wrappers, `web/public/maps/*.json` P-code joins.
- Supabase free tier: batch writes (`executemany`), short-lived connections,
  clear stale sessions if a pipeline crashes mid-run; DB ~500 MB, storage 1 GB
  (current usage is a tiny fraction; re-check with a size query when ingesting
  at municipality scale).

---

### P2B.S1 — The correct map of Nepal (Limpiyadhura / Lipulekh / Kalapani)

**GOAL (plain language):** Replace the portal's 2017-vintage boundary files
with ones matching Nepal's official political map (Survey Department, May
2020), which includes the Limpiyadhura–Lipulekh–Kalapani territory in Darchula
district. Record the boundary policy as a decision.

**WHY IT MATTERS:** A Nepal data portal showing the pre-2020 map is a
credibility and correctness failure — arguably the single most visible error a
Nepali visitor could find. Only Darchula's geometry (and the national outline)
changes; all P-code data joins are untouched.

**PREREQUISITES:** none. **TIME ESTIMATE:** 90–120 min (mostly recon).

**ACTIONS:**
1. Instruct the implementing model:
   > "FIRST verify the problem: load `web/public/maps/nepal-districts.json`,
   > find the Darchula feature (DIST_PCODE NP0709 — verify the code from the
   > file, don't assume), and report its maximum longitude/latitude extent.
   > Nepal's official 2020 map extends Darchula's northwest to include
   > Limpiyadhura (≈ lon 80.52, lat 30.44) and Lipulekh (≈ lon 81.0, lat
   > 30.23); official national area changed 147,181 → 147,516 km². If our file
   > already includes that extent, STOP and report — no work needed.
   > OTHERWISE: recon openly-licensed GeoJSON derived from the official 2020
   > map. Candidate hunting grounds, in trust order: (a) Survey Department /
   > National Geoportal (dos.gov.np, nationalgeoportal.gov.np) downloads;
   > (b) OCHA/HDX 'COD-AB NPL' updates dated after May 2020; (c) Open
   > Knowledge Nepal / opendatanepal.com; (d) GitHub repos updated post-2020
   > (search 'nepal geojson 2020 limpiyadhura'). For each candidate verify:
   > (1) Darchula includes the region above; (2) 77 districts / 7 provinces
   > with P-codes present OR name fields we can join to our existing P-code
   > mapping (reuse the alias table from reference/census/PROVENANCE.md —
   > dhanusa/kavrepalanchok/makwanpur); (3) total area within 1% of 147,516
   > km²; (4) an explicit open license. NEVER trace or hand-draw a boundary.
   > If no candidate passes all four checks, STOP and present the founder the
   > closest candidates with what each fails — do not swap.
   > On success: store the raw source + license + URL + retrieval date under
   > `reference/geo/official-2020/` with a PROVENANCE.md; simplify with
   > mapshaper (same settings as before: districts ~4%, provinces ~8%,
   > `keep-shapes`, precision 0.0001, keep only P-code + name fields); write
   > to `web/public/maps/`; confirm the /population map still joins all 77
   > values (no grey districts); write `docs/decisions/0004-official-map.md`
   > ('the portal renders the Survey Department 2020 political map; boundary
   > files must verify against it')."
2. Founder eyeball: the northwest corner of the district map visibly includes
   the extended Darchula wedge.

**VERIFICATION CHECKLIST:**
- [ ] Darchula extent includes ≈(80.52E, 30.44N); national area within 1% of
      147,516 km² (report the computed number).
- [ ] All 77 districts still join by P-code on /population (0 no-data regions).
- [ ] Raw source + license archived under `reference/geo/official-2020/`;
      decision 0004 written.
- [ ] File sizes remain ≤ ~350 kB per map file.

**IF IT GOES WRONG:** No verifiable open source found → STOP with a written
options memo (this is a "report, never guess" boundary; an unofficial trace is
worse than the status quo with a visible disclaimer). Interim fallback the
founder may approve: keep old files but add a map-footnote "boundaries shown
are pre-2020 vintage; update in progress."

**COMMIT:** `P2B.S1: official 2020 map of Nepal (Limpiyadhura/Lipulekh) + decision 0004`

---

### P2B.S2 — Scheduled ingestion (the staleness fix)

**GOAL:** Every pipeline runs itself on a schedule; failures alert the founder;
the site can say "last updated."

**WHY IT MATTERS:** Manual-only pipelines mean silent staleness — the quiet
death of a "trustworthy" portal. Every dataset added after this step inherits
automation for free.

**PREREQUISITES:** none (do before the data expansions). **TIME:** 90 min.

**ACTIONS:**
1. Instruct the implementing model:
   > "Create `.github/workflows/ingest.yml`: two scheduled jobs — weekly
   > (`ingest-wb`, Sundays) and monthly (`nrb-bfs-acquire` → `extract` →
   > `status`, day 20; NRB publishes mid-month) — plus `workflow_dispatch` for
   > manual runs. Each job: checkout, Python 3.12, `pip install -e .`, run the
   > make target, and FAIL LOUDLY on nonzero exit (GitHub emails the founder).
   > NRB promote stays HUMAN-GATED: the workflow runs acquire+extract and, if
   > extract staged anything new, prints a clear 'staged N rows — review and
   > promote locally' notice into the job summary (do NOT auto-promote; the
   > review gate is rule 3). Census gets NO schedule (decennial). Secrets:
   > DATABASE_URL + SUPABASE_URL/SUPABASE_SERVICE_KEY/STORAGE_BUCKET as GitHub
   > Actions secrets — walk the founder through adding them in Settings →
   > Secrets (values from local .env; announce before, founder pastes).
   > Add `GET /v1/meta` to the API: per dataset, latest successful
   > ingestion_log finished_at + latest release_date (read-only, tested with
   > the fake repo). Surface 'Data updated: {date}' in the site footer from
   > /v1/meta. Update keep-alive.yml comment to note ingest.yml also provides
   > DB activity."
2. Trigger each workflow once via workflow_dispatch; confirm green runs and
   that a deliberately-broken dry run (bad env on a branch) actually fails.

**VERIFICATION CHECKLIST:**
- [ ] Both scheduled jobs exist, manual-triggered once, green.
- [ ] A forced-failure test run notifies (founder sees the email).
- [ ] `/v1/meta` returns real dates; site footer shows them.
- [ ] NRB job never promotes on its own.

**IF IT GOES WRONG:** Actions can't reach Supabase → same IPv4/pooler rule as
Vercel (memory: render-supabase-pooler-deploy); use the pooler DSN in the
secret. Scheduled workflows pause after ~60 days without repo pushes — the
weekly WB job's own commits don't count; note in README that any push resets it.

**COMMIT:** `P2B.S2: scheduled ingestion + /v1/meta freshness (automation before expansion)`

---

### P2B.S3 — World Bank full mirror (~1,400 indicators)

**GOAL:** Every WDI indicator with real Nepal data lives in the warehouse with
verified metadata, auto-assigned sector and unit — junk filtered out.

**WHY:** Instant breadth from the cheapest source; the sector pages (P2B.S5)
need this depth to feel real.

**PREREQUISITES:** P2B.S2. **TIME:** 2 sessions (S3a enumerate+curate, S3b load).

**ACTIONS:**
1. Session A — instruct:
   > "Write `scripts/wb_catalog.py`: enumerate ALL of WB source 2 via
   > `/v2/source/2/indicator` (paged); for each, fetch Nepal presence via
   > `/v2/country/NPL/indicator/{code}?format=json&per_page=1&mrnev=1`.
   > KEEP if: has ≥1 non-null Nepal value dated ≥2000 AND not in the WDI
   > archive. UNIT INFERENCE from the name/unit string, exact rules:
   > name contains '(%' or unit contains '%' → PCT; '(current US$)' or
   > '(constant' US$ → USD; 'per 1,000 live births' → PER_1000_LIVE_BIRTHS;
   > '(years)' → YEARS; a pure headcount ('number', 'total' populations) →
   > PERSONS or COUNT. TOPIC MAPPING from WB topic → our 8 (economy, population,
   > labor, health, education, agriculture, environment, governance):
   > Economy&Growth/Financial Sector/Trade/External Debt/Public Sector/Poverty
   > → economy (finance split happens at display, P2B.S5); Health/Nutrition →
   > health; Education → education; Labor & Social Protection → labor;
   > Agriculture & Rural → agriculture; Environment/Energy/Climate/Urban →
   > environment; Gender/Social Development → population unless name clearly
   > fits another; Science&Tech/Infrastructure → economy. ANY indicator whose
   > unit or topic cannot be resolved by these rules goes to
   > `reference/worldbank/unmapped_report.csv` and is NOT loaded (report,
   > never guess). Output: `db/seeds/indicators_wb_full.csv` + a summary
   > (kept / dropped-no-data / dropped-archived / unmapped counts). Commit the
   > CSV so the catalog is reviewable and stable."
2. STOP-point (the one founder checkpoint in this file): founder skims the
   summary counts + 20 random rows read aloud in plain language. Then:
3. Session B — instruct:
   > "Extend seeding to load indicators_wb_full.csv (same verified-metadata
   > flow as the existing 20 — names/definitions from the live metadata API;
   > keep the original 20 codes' identities stable). Run `make ingest-wb`
   > (it iterates whatever indicators exist — confirm it batches inserts with
   > executemany and short connections at this new scale BEFORE running; if it
   > is row-by-row, fix that first — Supabase lesson). Expect tens of
   > thousands of observations. Quality gate: existing rules apply; add bands
   > only where a new unit class appears. Spot-check 5 indicators against
   > data.worldbank.org pages, exact values. Prove idempotency (re-run → 0
   > loaded)."

**VERIFICATION CHECKLIST:**
- [ ] Catalog CSV committed with summary counts; unmapped report exists and is
      small relative to kept (if unmapped > ~15%, improve rules, don't force).
- [ ] Warehouse holds the new indicators; `make ingest-wb` idempotent at scale;
      lint/test green; 5/5 spot-checks exact.
- [ ] /v1/indicators still fast (<2s cold); if not, add the obvious index and
      note it.

**IF IT GOES WRONG:** WB API rate-limits the enumeration → cache responses to
the raw lake and resume; never hammer. Metadata fetch fails for a code → it
lands in the failures report exactly like the existing seed flow.

**COMMIT (2):** `P2B.S3a: WB full catalog — curated, unit/topic-mapped, junk filtered`
· `P2B.S3b: WB full mirror loaded (idempotent at scale)`

---

### P2B.S4 — The headline-answer policy (one number per question)

**GOAL:** For any concept covered by multiple sources (population: census vs
WB), the portal has ONE headline answer; alternatives are shown, labeled, never
hidden. Recorded as decision 0005.

**WHY:** Two different "populations of Nepal" on one site erodes trust faster
than any missing feature.

**PREREQUISITES:** P2B.S3 (the collisions now exist at scale). **TIME:** 60 min.

**ACTIONS:**
1. Instruct:
   > "Write `docs/decisions/0005-headline-answers.md`: RULE — for Nepali-counted
   > facts (population, households, literacy at census years) the NSO census is
   > headline and WB is 'modeled estimate'; for internationally-modeled series
   > (GDP, trade, comparisons) WB is headline; for banking/monetary, NRB.
   > Wire `indicators.preferred_source_id` accordingly for colliding concepts
   > (the census/WB population + literacy pairs at minimum — enumerate
   > collisions by matching topic+name patterns and LIST them in the decision
   > doc). Frontend contract: wherever both appear (sector pages, search),
   > the non-preferred series renders with an 'alternative estimate — {source}'
   > badge. No data is deleted or hidden — this is labeling only."

**VERIFICATION CHECKLIST:**
- [ ] Decision 0005 lists the actual collision pairs found.
- [ ] preferred_source_id set for them; API exposes enough for the frontend to
      badge (add the field to /v1/indicators if absent).

**IF IT GOES WRONG:** A collision is genuinely ambiguous → put it in the
decision doc's "unresolved" table with both options; founder decides next
session. Never pick silently.

**COMMIT:** `P2B.S4: headline-answer policy (decision 0005) + preferred sources wired`

---

> **Implementation spec exists:** P2B.S5 and P2B.S6 have a full
> implementation-grade spec at **`docs/specs/frontend-sector-portal-spec.md`**
> (authored with Fable 5; all design decisions pre-made — exact sector
> configs, curated chart codes, component contracts, orbit geometry and
> animation values, a11y requirements, Playwright + screenshot protocol, and
> the known traps). The implementing model follows the SPEC for the how; the
> steps below remain the acceptance gates. Kickoff prompt to paste:
> *"Read docs/specs/frontend-sector-portal-spec.md fully, then implement it
> exactly — execute and verify, do not redesign. Acceptance gates are P2B.S5
> and P2B.S6 in docs/steps/phase-2b-expansion-steps.md. Stop at the spec's §8
> STOP for founder screenshot approval before deploying."*

### P2B.S5 — Sector portal: IA + dashboard-style sector pages (absorbs P3.S2)

**GOAL:** Navigation reorganized by SECTOR per decision 0003. Each sector page:
curated headline charts on top (dashboard style — founder's choice), full
searchable indicator list below, source badges everywhere.

**WHY:** This is the founder's core product vision: data by sector, mixing
sources, with sources as trust labels — and it's what makes 1,400 indicators
usable.

**PREREQUISITES:** P2B.S3, P2B.S4. **TIME:** 2 sessions (routes+one exemplar;
then the rest + search + Playwright).

**ACTIONS:**
1. Sector set (locked with founder): **Economy** (`/economy`), **Finance &
   Banking** (`/finance` — NRB series + WB financial-sector), **People &
   Population** (`/people` — census + WB demographics; links into /population
   map), **Health** (`/health`), **Education** (`/education`), **Labor**
   (`/labor`), **Agriculture & Environment** (`/environment`), **Governance**
   (`/governance`). DB topics map 1:1 except: economy splits into
   Economy/Finance at display via a curated code list; agriculture+environment
   share a page (two tabs or two sections).
2. Instruct (session A):
   > "Build the sector-page template in the existing design system: page head
   > (sector name, one-line description, count of indicators + sources); a
   > HEADLINE band of 3–5 curated charts (each sector's curated codes listed in
   > `web/lib/sectors.ts` — write it as reviewable data, with WHY-this-chart
   > comments); below, the full indicator list for the sector: client-side
   > filter box, grouped sensibly, each row showing name + years covered +
   > source badge, clicking opens the existing explorer view for that
   > indicator (route it as /explore?indicator=CODE — make explore read the
   > query param). Alternative-estimate badges per decision 0005. Build
   > `/economy` fully as the exemplar. Update header nav: sector dropdown or
   > a second nav row (mobile-checked); keep Overview + Population map links."
3. Instruct (session B):
   > "Roll the template to the remaining sectors; add `/search` (client-side
   > index over code+name+topic of /v1/indicators — no backend change); add a
   > Playwright smoke test (P2 lesson 5): landing renders, one sector page
   > renders a real chart canvas with nonzero pixels, /population paints the
   > map, search finds 'GDP'. Wire into CI. Bundle discipline: sector pages
   > must stay <120 kB first-load (charts lazy)."

**VERIFICATION CHECKLIST:**
- [ ] All 8 sector routes live; source badges + alternative-estimate labels
      present; every chart still shows provenance.
- [ ] 1,400 WB indicators reachable but never rendered as one flat list.
- [ ] Playwright smoke green in CI; first-load budgets met.
- [ ] The old source-shaped pages redirect or re-frame (banking → /finance
      keeps its URL as the NRB dashboard within Finance).

**IF IT GOES WRONG:** Curated headline picks feel arbitrary → they're data
(`sectors.ts`), founder can re-order with plain-language notes; don't block on
taste. Search too slow client-side at 1,400 → memoize + prefix index before
reaching for a backend.

**COMMIT (2):** `P2B.S5a: sector IA + /economy exemplar (decision 0003 realized)`
· `P2B.S5b: all sector pages + search + Playwright smoke`

---

### P2B.S6 — The landing page: "Nepal in orbit" (unique, but trustworthy)

**GOAL:** A landing page nobody mistakes for a template — the founder's
"solar-system" inspiration executed tastefully: a central Nepal with the 8
sectors in orbit, each carrying a live number, doubling as navigation.

**WHY:** The homepage is the pitch. Distinctive + fast + credible beats safe.

**PREREQUISITES:** P2B.S5 (sectors exist to orbit). **TIME:** 1–2 sessions.

**ACTIONS:**
1. Instruct:
   > "Design constraints, non-negotiable: keep the design system (paper, ink,
   > crimson, Fraunces/Inter) — the orbit is drawn WITH our palette, not a
   > dark 'space' theme; total added JS ≤ 40 kB (hand-rolled SVG + CSS
   > animation or a tiny canvas loop — NO new framework/library); honors
   > `prefers-reduced-motion` (static radial layout, no spin); fully usable
   > with keyboard + screen reader (the orbit is progressive enhancement over
   > a plain sector list that is ALWAYS in the DOM); mobile gets the compact
   > radial or stacked cards, chosen by what actually fits, not scaled-down
   > desktop. CONCEPT: center = Nepal map silhouette (reuse province geojson,
   > flattened to a single outline at build time); 8 sector nodes orbit slowly
   > (60s+ period, barely-moving is classier than spinning); each node = sector
   > name + ONE live number from the API (reuse HeroStats fetch pattern, cached,
   > skeletons); hover pauses + lifts the node; click navigates. Below the
   > fold: keep the existing trust strip + stat tiles. Build it, screenshot at
   > 360/768/1440 via Playwright, and STOP: present screenshots to the founder
   > for the go/no-go BEFORE deploying — if it reads gimmicky, the fallback is
   > the current hero + the orbit demoted to a decorative corner. The founder's
   > eye decides; the stranger test (P3.S14) can veto later."

**VERIFICATION CHECKLIST:**
- [ ] JS budget kept (report numbers); reduced-motion + keyboard verified.
- [ ] Live numbers real (spot-check 2 against /v1 endpoints).
- [ ] Founder approved screenshots BEFORE deploy (the explicit STOP).
- [ ] Lighthouse performance ≥ 90 on the landing page.

**IF IT GOES WRONG:** Looks kitsch → fallback path above, no sunk-cost
defending. Perf blows the budget → cut animation before cutting content.

**COMMIT:** `P2B.S6: landing page — Nepal data orbit (accessible, on-budget)`

---

### P2B.S7 — Census: every topic, province + district

**GOAL:** All census topic families in the warehouse and on the map/table UI —
age structure, religion, mother tongue, caste/ethnicity, marital status,
disability, households & facilities, migration/absentees, economic activity,
fertility, and the literacy/education families.

**WHY:** The census is the deepest uniquely-Nepali dataset; the map makes each
topic shine; the pipeline pattern is already proven.

**PREREQUISITES:** P2B.S1 (map), P2B.S2. **TIME:** 3–4 sessions, grouped.

**ACTIONS:**
1. Endpoint families (from the verified facts bank; each family = one parser +
   one session-group):
   - A: `/population/age-group` (pyramid data), `/population/marital-status`,
     `/population/first-marriage`
   - B: `/population/religion`, `/population/mother-tongue`,
     `/population/ancestor-language`, `/population/caste` (+ `/cast-ethnicity`)
   - C: `/population/disability`, `/population/disability-summary`,
     `/population/birth-registration`, `/population/living-arrangement`,
     `/population/household-head`
   - D: `/household` family + `/local-level-container/household-facility`,
     `/female-household-lead`
   - E: `/economic`, `/migration`, `/absent`, `/fertility`, remaining
     `/literacy` blocks (schoolByAttendance, educationByLevel,
     educationByField)
2. Per family, instruct:
   > "Fetch the family's endpoints for national + 2 provinces + 2 districts
   > FIRST; inspect real shapes; extend `census_layout.py` registry + parsers
   > in the established style (share-vs-count: prefer counts where the payload
   > has countSeries, store shares only when counts are absent — document per
   > indicator; breakdown keys named plainly: sex, age_group, religion,
   > language, caste, disability_type…). CHECK CARDINALITY before coding:
   > categories × 85 geos; anything generating >50k rows for one family, flag
   > and confirm the modeling (usually store top-N categories + 'other'? NO —
   > store ALL categories; it's the display that curates). Extend the quality
   > gate per family (shares sum ≈100 within rounding as an INFO check; counts
   > sum to known totals where the census guarantees it). Pipeline reuse:
   > same raw-lake paths `nso/census2021/<endpoint>/<geo>`, same release/
   > change-aware flow. Spot-check 2 values per family against the NSO site
   > UI (their dashboard renders these numbers — screenshot-compare) and, for
   > one family, against the published PDF report (independent channel).
   > Frontend: each new indicator appears in /population's picker (grouped by
   > family) and the sector pages via topics; breakdowns beyond sex get a
   > breakdown selector on the map (one breakdown value shaded at a time)."
3. **Sensitivity note (binding):** religion/caste/ethnicity/language layers
   ship with neutral presentation — alphabetical or population-order lists,
   no editorial ranking language, sequential palette only, and the census
   citation prominent. No commentary. (Founder-reviewed framing can come
   later; the default is restraint.)

**VERIFICATION CHECKLIST (per family):**
- [ ] Parser fails loudly on unknown labels; registry⇄CSV test extended.
- [ ] Spot-checks exact (2 per family; 1 PDF-verified family overall).
- [ ] Idempotent re-run; quality gate INFO/failure behavior demonstrated.
- [ ] Map renders the family's headline indicator at both levels.

**IF IT GOES WRONG:** An endpoint's shape varies by level (some do) → parser
branches per level with tests for each, or the level is skipped WITH a note in
the indicator definition — never a silent partial load.

**COMMIT (per family):** `P2B.S7x: census <family> — parsed, gated, mapped`

---

### P2B.S8 — Census municipality level (753) + geographic drill-down UI

**GOAL:** Local-unit geographies seeded; municipality-level values for the
topics that have them; the census section gets national → province → district
→ municipality drill (map + tables), showing only levels that exist per topic.

**PREREQUISITES:** P2B.S7 (at least families A+B done). **TIME:** 2 sessions.

**ACTIONS:**
1. Instruct (data session):
   > "Extract the full municipality list from the NSO frontend JS (the
   > embedded array with district/value/label/no_of_wards — the extraction
   > pattern is in reference/census/PROVENANCE.md; archive the raw extraction
   > like nso_districts_raw.json). Reconcile count against the official 753.
   > Seed as level='local_unit' with parent district by P-code; codes: use the
   > official local-unit P-codes if the boundary source (P2B.S1's provider or
   > the existing municipalities GeoJSON) carries them — verify a sample of 10
   > against district membership; if no P-codes are available, mint stable
   > codes `NP<district-pcode>-M<nso-id>` and DOCUMENT that in PROVENANCE (a
   > portal-internal scheme is honest; a guessed 'official' code is not).
   > name_ne: NSO np locale where keys match; missing ones stay NULL with a
   > count reported. Extend nso_geo_ids.csv; extend the census pipeline's geo
   > targets with `municipality=` param; ingest highlight + the P2B.S7
   > families that respond at municipality level (probe each; record which
   > don't). Expect ~10× district row counts; batch accordingly; check DB size
   > after (`select pg_database_size`) and report headroom."
2. Instruct (UI session):
   > "Census drill-down: /population gains a level selector including
   > municipality (map only if a verified municipalities boundary file exists
   > and joins ≥95% of units — else table-only for that level, stated on the
   > page); clicking a district on the map drills to its municipalities table;
   > breadcrumbs national → province → district. Per-topic level availability
   > comes from the data (which levels have rows), never hardcoded."

**VERIFICATION CHECKLIST:**
- [ ] 753 local units, each under the right district; sample of 10 verified;
      idempotent.
- [ ] Which-topics-have-municipality documented from probing, not assumed.
- [ ] Drill UI: levels reflect actual data; no empty maps.
- [ ] DB size reported with headroom.

**IF IT GOES WRONG:** Municipality boundary file won't join cleanly → ship
table-only at that level (honest) and open a follow-up; never force fuzzy
name-joins on 753 units.

**COMMIT (2):** `P2B.S8a: 753 local units seeded + municipality-level census data`
· `P2B.S8b: census drill-down UI (map/table by availability)`

---

### P2B.S9 — NRB Tier A: the other aggregate tables (C5–C7)

**GOAL:** Deposit/loan levels and the other aggregate BFS tables join the 35
C4 indicators — same files, deeper cut.

**PREREQUISITES:** P2B.S2. **TIME:** 2–3 sessions.

**ACTIONS:**
1. Instruct:
   > "Recon FIRST across all 59 archived raw files (they're in the lake —
   > no re-download): map which tables beyond C4 are structurally stable
   > across every file (the C4 recon found older 14/18/20-table eras differ
   > outside C4 — quantify that for C5–C7: sheet names, header rows, row
   > labels). Produce a stability report BEFORE writing a parser. Then extend
   > `bfs_layout.py` with per-table registries exactly like C4 (normalizer,
   > fail-loudly on unknown labels), covering only the stable range; earlier
   > eras go to a follow-up, stated. Units: these are NPR levels — add an
   > NPR_MILLIONS unit (verify the files' stated unit — 'Rs. in million' vs
   > crore — from the sheets themselves, per file era). Same staging → review
   > → promote gate as C4 (rule 3: human-made Excel). Spot-check 3 values
   > against the printed files. Frontend: new indicators appear in the
   > banking dashboard picker under new sections."

**VERIFICATION CHECKLIST:**
- [ ] Stability report committed; parser covers only proven-stable ranges.
- [ ] Unit verified from the files (never assumed million vs crore).
- [ ] Staging review shown; promote gated; 3/3 spot-checks exact; idempotent.

**IF IT GOES WRONG:** A table's labels wobble era-to-era → registry per era
with explicit valid-from/to files, or defer that table with a note. Unknown
label = failed run, always.

**COMMIT:** `P2B.S9: NRB BFS aggregate tables C5–C7 (stability-proven ranges)`

---

### P2B.S10 — NRB Tier B: per-bank data — SCOPING ONLY

**GOAL:** A written scoping memo (not code): what per-bank ingestion requires,
so the founder can decide with eyes open.

**WHY:** ~110 institutions × monthly × mergers/renames/license-exits needs a
bank registry (its own reference data with validity windows) — a real design
decision, not a bolt-on.

**PREREQUISITES:** P2B.S9. **TIME:** 60–90 min, no code.

**ACTIONS:**
1. Instruct:
   > "From the 59 archived files, extract the per-bank table inventory: which
   > tables, how many banks per class per month, name-change/merger events
   > visible across the window (list them), and the modeling options for a
   > `bank_registry` (codes, validity, merger lineage) with pros/cons. Estimate
   > row volumes and DB impact. Deliver `docs/decisions/0006-per-bank-scope.md`
   > DRAFT with a recommendation. STOP — founder decides."

**COMMIT:** `P2B.S10: per-bank scoping memo (decision 0006 draft)`

---

### P2B.S11 — The "give me a link" source-onboarding template

**GOAL:** A reusable template so that when the founder pastes any new data
link, a recon session produces a step file exactly like the ones above —
judgment front-loaded, implementation mechanical.

**ACTIONS:**
1. Instruct:
   > "Write `docs/runbooks/source-recon-template.md` with the standard recon
   > protocol distilled from the census onboarding: (1) identify the real data
   > channel behind the page (API? files? embedded JS?) with the techniques
   > used on censusresults (network base URLs in JS bundles, locale files,
   > embedded arrays); (2) verify authority + license; (3) capture raw
   > evidence under reference/<source>/ with PROVENANCE.md; (4) map source ids
   > ⇄ our codes with fail-loudly alias rules; (5) define indicators registry
   > + units + topics; (6) define quality-gate bands with rationale; (7) list
   > spot-check values from an independent channel; (8) write the step file in
   > the house format (GOAL/WHY/PREREQ/ACTIONS/CHECKLIST/IF-WRONG/COMMIT).
   > Include the founder workflow at top: 'Founder pastes a URL and says
   > /recon → the session fills this template → output is
   > docs/steps/onboard-<source>.md → any model implements it.'"

**COMMIT:** `P2B.S11: source-recon template — link in, step file out`

---

## Suggested order & session count

S1 (map, do first — visible correctness) → S2 (automation) → S3a/S3b (WB) →
S4 (policy) → S5a/S5b (sector portal) → S6 (landing) → S7 A–E (census topics)
→ S8a/S8b (municipality) → S9 (NRB C5–C7) → S10 (scoping memo) → S11
(template). ≈ 16–20 sessions. S7 onward can interleave with Phase 3 steps that
don't collide (P3.S3 bilingual, P3.S9 downloads); S1–S6 should not be
reordered.

**Standing rules for every step:** verification gates (`make lint`,
`make test`, `cd web && npm run build`) green before any commit; raw before
parsed; idempotent; report-never-guess; PROJECT_LOG entry every session; plain
language to the founder; announce commands.
