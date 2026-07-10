# PHASE 4 — INDUSTRIAL STRENGTH — Step File

**Version 0.9 — DRAFT, July 2026**
**Governed by: Master Prompt v1.0 · Architecture Blueprint v1.0**
**Assumes: Phase 3 exit criteria fully met (portal deployed, stranger test passed — see docs/steps/phase-3-steps.md and the P3.S14 log entry).**

> **DRAFT STATUS:** The Master Prompt (§4) requires step files to be finalized only when the previous phase nears completion. This draft was written mid-Phase-2 at the founder's request. **Before starting P4.S1: re-read the P3.S14 PROJECT_LOG lessons, fill in the carry-forward section below, adjust any step this invalidates, and bump this file to Version 1.0.**

**Phase goal: make the system run itself and tell you when it's unwell. Pipelines move onto a schedule under Dagster, failures and stale data raise alerts, data-quality coverage widens, two more international sources (IMF, ILO) and the ministry-PDF workflow come online, the performance budgets are measured and met under load, and the backup/restore story is proven — not assumed.**

**Why now:** Phase 3 put the portal in front of the public; from here, silent staleness or a quiet pipeline failure damages trust in a way a missing feature never could. Everything in this phase converts "the founder remembers to run it and eyeballs it" into "the system runs it, tests it, and reports it." Correctness came first (Phases 1–2), visibility second (Phase 3), automation now — exactly the blueprint's ordering.

**Total founder time: ~14–19 hours across 12 steps. One step per session. Never two.**
**Phase exit criterion: all pipelines run on schedule without founder action; a deliberately-broken pipeline raises an alert within its cycle; IMF and ILO series are live and cited; a ministry PDF number reaches the portal only through the authenticated review UI; the §3.5 latency budgets hold under load; and a full restore drill from backup succeeds. And the P4.S12 checklist passes.**

**How to run every session:** open Claude Code in the project folder, open this file, and tell Claude Code: "We are on step P4.SX of docs/steps/phase-4-steps.md. Follow it under the master prompt." Approve actions one at a time; verify with the checklist; commit; log.

---

## Carry-forward lessons from Phase 3 (apply in every step)

**TO BE FILLED AT P3.S14 CLOSE from the PROJECT_LOG "lessons for Phase 4" entry.** Expected candidates (verify against the actual log; delete what didn't happen, add what did):

1. *(placeholder)* Branch-per-step workflow is mandatory (adopted P3.S1) — every P4 step on `step/P4-SX-…`, merged after verification; CI gates the deploy.
2. *(placeholder)* Playwright against the deployed URL is part of "green"; anything touching the API or web re-runs it.
3. *(placeholder)* Production hosting quirks discovered in P3.S13 (free-tier sleep, cold starts) — orchestration schedules must account for them.
4. *(placeholder)* UTF-8 stdout helper remains mandatory in every script Dagster will run.
5. *(placeholder — add real lessons from PROJECT_LOG here)*

---

### P4.S1 — Dagster stands up: one pipeline becomes a job

**GOAL (plain language):** Install Dagster (the pipeline scheduler/monitor) and wrap our cleanest existing pipeline — World Bank ingestion — as a Dagster job, run manually from the Dagster UI, changing none of the pipeline's logic.

**WHY IT MATTERS:** Blueprint §6: Dagster arrives in Phase 4, after correctness. Wrapping the best-understood pipeline first proves the harness on something we trust — the same principle as dbt's introduction in P2.S3.

**PREREQUISITES:** Phase 3 complete; this file bumped to v1.0 with real carry-forward lessons.
**TIME ESTIMATE:** 90–120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Add Dagster to the project (pinned in pyproject) with an `orchestration/` module. Wrap the existing World Bank ingestion as a Dagster job that calls the SAME code the Makefile target calls — no logic forked into Dagster. It reads env config the same way and writes the same ingestion_log rows. `make dagster-dev` starts the local UI. Run the job once from the UI and show me the run log side by side with the ingestion_log row it produced."
2. Run it from the UI; confirm the warehouse state is unchanged where it should be (idempotency holding under a new runner).

**VERIFICATION CHECKLIST:**
- [ ] Dagster UI shows the World Bank job green; the run wrote a normal `ingestion_log` row.
- [ ] Re-run produces no duplicates (idempotency proven under Dagster).
- [ ] `make ingest-wb` still works unchanged — the Makefile path and the Dagster path share one implementation.

**IF IT GOES WRONG:** The temptation is to rewrite the pipeline "Dagster-style" — don't. If wrapping forces a code change, make it a refactor both paths use, tested before and after.

**COMMIT:** `P4.S1: Dagster harness — World Bank pipeline as first job`

---

### P4.S2 — All pipelines onto the schedule

**GOAL (plain language):** Bring every existing pipeline (NRB acquire/stage, census, dbt build+test) under Dagster and give each a schedule matching its source's real publication rhythm — with the review gate still human, never scheduled away.

**WHY IT MATTERS:** Master Prompt §5 P4: orchestration + schedules. The scheduler must encode a crucial distinction: acquisition and staging can be automatic; *promotion of messy-source data stays behind the human review gate* (Blueprint §5.4) forever.

**PREREQUISITES:** P4.S1.
**TIME ESTIMATE:** 90–120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Wrap the remaining pipelines as Dagster jobs: NRB acquire+stage (CPI, monetary, forex), census (manual-trigger only — censuses don't recur), and dbt run+test as a job downstream of ingestions. Schedules follow the catalog's update_frequency: World Bank monthly, NRB per its publication cycle. The NRB jobs stop at staging with review_status='pending' and NOTIFY that review is waiting — promotion remains exclusively the human `make review`/`make promote` path; assert in code/tests that no Dagster job calls promote. Document the schedule table in docs/runbooks/orchestration.md."
2. Trigger the NRB job; confirm it stops at staging and the review-waiting notification fires.

**VERIFICATION CHECKLIST:**
- [ ] Every pipeline visible in Dagster with a schedule (or explicit manual-only marking) documented in the runbook.
- [ ] A scheduled NRB run lands in staging as pending and notifies; nothing auto-promotes (test proves no job reaches promote).
- [ ] The dbt job runs downstream of ingestion jobs and its tests gate the run's green status.

**IF IT GOES WRONG:** A schedule fires while the dev DB is paused (the Supabase free-tier lesson) → the job must fail loudly and alert (next step), not hang; note this failure mode in the runbook now.

**COMMIT:** `P4.S2: all pipelines scheduled under Dagster (review gate stays human)`

---

### P4.S3 — Monitoring and alerting: the system reports its own health

**GOAL (plain language):** Make failure and staleness impossible to miss: any failed job, any source past its expected update window, and any dbt test failure sends the founder an alert (email or messaging app), and a simple status page summarizes pipeline health.

**WHY IT MATTERS:** Master Prompt §5 P4: monitoring/alerting on failures and freshness. A public portal that silently serves stale data is worse than one that's down — this step is the trust-preservation layer.

**PREREQUISITES:** P4.S2.
**TIME ESTIMATE:** 90–120 minutes.

**ACTIONS:**
1. Founder decision: the alert channel (email is fine; whatever you actually read daily).
2. Instruct Claude Code:
   > "Wire Dagster failure alerts to [channel]. Configure dbt source-freshness per dataset's update_frequency and schedule a freshness-check job that alerts when a source is stale beyond tolerance. Add an internal `/status` view (authenticated or unlinked): last run + outcome per pipeline, staging rows awaiting review, freshness per source. Then prove it: break the World Bank job deliberately (bad URL, on a branch), let it run, and show me the alert arriving; then revert."
3. Watch the deliberate-failure alert arrive on your phone. Revert.

**VERIFICATION CHECKLIST:**
- [ ] The deliberate failure produced an alert in the chosen channel within the run's cycle; the revert restored green.
- [ ] Freshness config exists for every dataset; an artificially-backdated freshness check alerts.
- [ ] `/status` shows honest per-pipeline state incl. the pending-review count.

**IF IT GOES WRONG:** Alert fatigue is the real failure mode — one alert per root cause, not per retry; tune before adding channels.

**COMMIT:** `P4.S3: monitoring, freshness checks, and alerting proven by deliberate failure`

---

### P4.S4 — dbt coverage: the data dictionary grows teeth

**GOAL (plain language):** Widen dbt from "first models" to full coverage: every model described, every critical column tested (not_null, unique, accepted_values, relationships), value-range tests for known-bounded indicators, and regenerated dbt docs as the internal data dictionary.

**WHY IT MATTERS:** Master Prompt §3.4 and §5 P4. With scheduled automation (P4.S2–S3), tests are the only reviewer that looks at every run — coverage gaps are now unwatched pipelines.

**PREREQUISITES:** P4.S3.
**TIME ESTIMATE:** 90–120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Audit the dbt project: list every model/critical column lacking a description or test. Fill the gaps: schema tests per §3.4, plus data tests encoding real-world bounds (percentages 0–100, populations > 0, period continuity per series, every observation's geography/period/indicator resolves). Generate dbt docs and add `make dbt-docs`; note in the README how to open them. Report the before/after test count honestly."
2. Review the docs site: pick one model and confirm you (the founder) can understand what it holds from the descriptions alone.

**VERIFICATION CHECKLIST:**
- [ ] No model without a description; no critical column untested (the audit list proves it).
- [ ] `make dbt-test` green, with materially more tests than before (counts logged).
- [ ] dbt docs open locally and read as a usable data dictionary.

**IF IT GOES WRONG:** New tests fail on old data → that's a discovery, not an obstacle; investigate each failing row before loosening any test. Loosening requires a comment explaining the real-world reason.

**COMMIT:** `P4.S4: dbt coverage expanded — descriptions, tests, docs as data dictionary`

---

### P4.S5 — IMF pipeline (SDMX)

**GOAL (plain language):** Onboard the IMF as the project's third international source via its SDMX API — the standard machine-readable format used by statistical agencies — reusing the raw-first, idempotent, release-tracked pattern end to end.

**WHY IT MATTERS:** Blueprint §1 lists IMF second among initial sources; SDMX experience also prepares for other agencies later. As a clean API source it follows the World Bank pattern (no staging gate needed per §3.3) — proving the pattern stretches to a second API shape.

**PREREQUISITES:** P4.S4.
**TIME ESTIMATE:** 120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Walk docs/runbooks/adding-a-data-source.md for the IMF. Register source + dataset(s); pick ~6–10 headline Nepal series (e.g. government finance, balance of payments — propose a list with the source's own codes for founder approval). Build `ingestion/imf/`: SDMX fetch → raw lake (per the source-keyed path convention) → parse → map to seeded indicators/units/periods → quality gate → observations under a release. Idempotent; offline fixture test; Dagster job + schedule; freshness config. Never guess a series mapping — unmapped codes are logged and skipped (Prime Directive 7)."
2. Founder approves the series list. Run; spot-check one value against the IMF's own site.

**VERIFICATION CHECKLIST:**
- [ ] IMF series in `observations`, cited, spot-checked against the IMF site.
- [ ] Raw SDMX payloads in the lake with hash + URL; pipeline idempotent on re-run.
- [ ] Dagster schedule + freshness live for IMF; `make test` green with new fixtures; new indicators/units came via seed files.

**IF IT GOES WRONG:** SDMX is dimension-heavy; a wrong dimension slice silently returns a different series → the fixture test must pin the exact query key, and the spot-check against the public site is non-negotiable.

**COMMIT:** `P4.S5: IMF SDMX pipeline (third international source)`

---

### P4.S6 — ILOSTAT pipeline

**GOAL (plain language):** Onboard ILOSTAT (labor statistics — employment, unemployment, labor-force participation for Nepal), the fourth international source, as another repetition of the proven API pattern — this time exercising the `breakdowns` column (sex, age) for real.

**WHY IT MATTERS:** Blueprint §1 source list; labor data is among the most requested categories for Nepal. By the second repetition, onboarding a clean source should be routine — this step measures how true that is.

**PREREQUISITES:** P4.S5.
**TIME ESTIMATE:** 90–120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Onboard ILOSTAT per the runbook: source + dataset registration, ~6–8 headline Nepal labor series (propose with ILO codes for approval), `ingestion/ilo/` raw-first idempotent pipeline, breakdowns (sex, age) mapped into the JSONB breakdowns column with every key documented in the catalog (Blueprint §4.3), quality gate, Dagster job + schedule + freshness, offline fixture. Report honestly how much of the pattern was reused vs. newly written — if something core needed changing, flag it as an abstraction fix, not a special case."
2. Approve the series list; run; spot-check one value; view one series with a sex breakdown on the portal.

**VERIFICATION CHECKLIST:**
- [ ] ILO series live and cited; one breakdown series renders with its breakdown visible/selectable.
- [ ] Every breakdown key used is documented in the catalog.
- [ ] Reuse report: core pipeline code unchanged (or the abstraction fix is its own reviewed change).

**IF IT GOES WRONG:** Breakdown explosion (dozens of age bands) → ingest only the headline breakdowns agreed in the series list; more can come later by demand, not by default.

**COMMIT:** `P4.S6: ILOSTAT pipeline with documented breakdowns`

---

### P4.S7 — Ministry PDFs, part 1: extraction into staging

**GOAL (plain language):** Face the hardest source class: numbers that exist only in ministry PDFs (health, education, or budget — one publication to start). Extract a chosen table from a real PDF into the staging table, layout-specifically and versioned, with scanned-page handling if needed.

**WHY IT MATTERS:** Blueprint §5.4 exists for exactly this: extract → staging → human review → promote, and "each extraction script is specific to one publication's layout and is versioned with the raw files it was built for." Ministries are where the most Nepal-unique data lives.

**PREREQUISITES:** P4.S6.
**TIME ESTIMATE:** 120 minutes (the messiest step — start fresh).

**ACTIONS:**
1. Founder decision: which ministry publication first (Claude proposes 2–3 candidates with a recommendation based on data value and PDF quality).
2. Instruct Claude Code:
   > "Onboard [chosen publication]: source/dataset registration, raw PDF into the lake with provenance. Write `ingestion/ministries/<pub>/extract.py` for the ONE chosen table: text-layer extraction (pdfplumber or similar) if machine-readable, OCR only if scanned (and then flag every OCR'd value's status accordingly); map periods (likely BS fiscal years — use bs_calendar, never a formula) and geographies (via the resolver; unmatched → logged, never guessed); load to staging as pending. Document the page/table coordinates in comments, versioned to this file's hash. Offline fixture from the actual PDF pages. Values that fail to parse are logged and excluded — Prime Directive 7."
3. Run; read the staged rows against the open PDF, side by side, yourself.

**VERIFICATION CHECKLIST:**
- [ ] Staged rows match the PDF table on a manual side-by-side of at least five values, incl. any Devanagari headers handled correctly.
- [ ] Every staged row carries raw_file_ref to the exact PDF object; parse failures are in the log with reasons, not guessed into rows.
- [ ] Extraction is fixture-tested offline; nothing promoted yet.

**IF IT GOES WRONG:** OCR quality too poor to trust → stop; a manually-keyed staging path (typed by the founder from the PDF, still through review) is more honest than bad OCR. Decide with the founder rather than shipping doubt.

**COMMIT:** `P4.S7: first ministry PDF extracted into staging (layout-versioned)`

---

### P4.S8 — Ministry PDFs, part 2: the review UI

**GOAL (plain language):** Replace the CLI review with a small authenticated web page: the reviewer sees each staged value next to a snapshot of the PDF region it came from, and approves/rejects with a note — then promotes approved batches, exactly like the CLI did.

**WHY IT MATTERS:** Master Prompt §5 P4 names the "review UI". The CLI gate (P2.S9) worked for the founder; a UI with the PDF snippet beside the number makes review materially more reliable — and §3.8 requires admin surfaces behind authentication, not publicly linked.

**PREREQUISITES:** P4.S7.
**TIME ESTIMATE:** 120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Build an authenticated review area (Supabase Auth, founder account only, no public links): a queue of pending staging rows grouped by batch, each row showing extracted value/indicator/geography/period beside a rendered snippet of the source PDF region (from the documented coordinates), approve/reject with a required note on reject, and a 'promote approved batch' action calling the SAME promote.py the CLI uses — one promotion path, two frontends. The pending-row protection from P2.S9 must hold identically. CLI review remains available as fallback."
2. Review the P4.S7 batch in the UI: approve the good rows, reject one deliberately to test the path, promote, and see the values on the portal.

**VERIFICATION CHECKLIST:**
- [ ] Review UI requires login; a logged-out request is refused; nothing links to it publicly.
- [ ] The PDF snippet renders beside each value; a rejection requires and stores a note.
- [ ] Promotion via UI produces identical release/ingestion_log/is_latest behavior as the CLI (same code path, shown by the log).
- [ ] Promoted ministry values are live on the portal, cited to the ministry publication.

**IF IT GOES WRONG:** Snippet-to-value misalignment (coordinates drift between PDF editions) → coordinates are versioned to a specific file hash by design; a new publication edition means a new extractor version, not a tolerance hack.

**COMMIT:** `P4.S8: authenticated review UI over the shared promotion path`

---

### P4.S9 — Revision history goes public

**GOAL (plain language):** Surface the revision story on the portal: an indicator page can show that a value was revised — old value, new value, which release changed it — turning the is_latest machinery (proven in P2.S12) into a public trust feature.

**WHY IT MATTERS:** Master Prompt §5 P4: "revision history view." Blueprint principle 5: the portal shows latest by default but can reconstruct what was known at any time. Researchers *need* vintages; showing them is a differentiator no existing Nepali source offers.

**PREREQUISITES:** P4.S8.
**TIME ESTIMATE:** 90 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "API: add a revisions view — for a given indicator/geo/period(/breakdowns), all releases' values in release order (`/v1/data/revisions?...`), cached like everything else. Web: on the indicator page, observations with history get a subtle 'revised' marker; clicking opens a revision panel: each vintage's value, release date, and status, oldest first, with the source release cited. The chart continues to plot is_latest only — history is on demand, never silently mixed into a series. Playwright asserts the panel opens on a known revised cell (the P2.S12 one)."
2. Open the P2.S12 revised NRB cell on the portal and read its history panel.

**VERIFICATION CHECKLIST:**
- [ ] The known revised cell shows the marker; its panel lists both vintages with release dates, correctly ordered.
- [ ] Un-revised cells show no marker; charts still plot only is_latest.
- [ ] `/v1/data/revisions` is documented on the API docs page (P3.S11).

**IF IT GOES WRONG:** Ambiguity between a *revision* (same cell, new release) and a *breakdown sibling* → the panel query must match the full uniqueness key from Blueprint §4.2; if it shows unrelated rows, the key is incomplete.

**COMMIT:** `P4.S9: public revision history view (vintages on demand)`

---

### P4.S10 — Performance pass and load test

**GOAL (plain language):** Measure the API and portal against the master prompt's budgets — p95 < 300 ms cached / < 1.5 s uncached, LCP < 2.5 s — under realistic load, fix what misses, and record the numbers as the phase's performance baseline.

**WHY IT MATTERS:** Master Prompt §3.5 says these targets are "measured in Phase 4" — this is that step. The portal now has five sources and maps; Phase 3's assumptions need re-proving under load, because launch (Phase 5) brings the first real traffic spikes.

**PREREQUISITES:** P4.S9.
**TIME ESTIMATE:** 120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Load-test the deployed API (a standard tool like k6 or locust, scripted in `tests/load/`): a realistic mix (indicator data, search, CSV, the maps' geo queries) at stepped concurrency. Report p50/p95/p99 for cached and uncached separately, honestly. Where the budget misses: check cache hit rates first (headers, CDN behavior, ETag revalidation), then query plans (EXPLAIN the slow ones; new indexes must be justified in their migration comment per §3.2), then payload sizes. Re-run Lighthouse on the P3.S12 page set and compare against the logged Phase 3 numbers. Write the final numbers into docs/runbooks/performance-baseline.md. Add `make load-test`."
2. Read the before/after table with Claude Code; sign off that budgets are met or the misses have logged, justified exceptions.

**VERIFICATION CHECKLIST:**
- [ ] p95 cached < 300 ms and uncached < 1.5 s on the deployed API under the test load (numbers in the baseline doc).
- [ ] Cache hit rate measured; repeated identical requests are provably served from cache.
- [ ] Lighthouse budgets still hold after Phase 4's features; any Phase 3 regression fixed.
- [ ] Load-test scripts committed and re-runnable (`make load-test`).

**IF IT GOES WRONG:** Budgets miss only on free-tier cold starts → that's a hosting-tier decision for the founder (document cost vs. target), not a code fix; record the decision in docs/decisions/.

**COMMIT:** `P4.S10: performance baseline — budgets measured under load`

---

### P4.S11 — The restore drill: prove the backups

**GOAL (plain language):** Prove the project can survive disaster: restore the database from a real backup into a scratch instance, run the test suites against it, and re-verify the raw-lake → warehouse rebuild path — then write the tested procedure into the runbook.

**WHY IT MATTERS:** Master Prompt §5 P4: "backups verified"; §3.2 requires the restore procedure documented in `docs/runbooks/restore.md`. An untested backup is a hope, not a backup. The Quality Bar's rebuild-from-raw promise gets its full-scale test here too.

**PREREQUISITES:** P4.S10.
**TIME ESTIMATE:** 90–120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Take a fresh `pg_dump` (named, per Prime Directive 4). Restore it into a scratch database (separate instance/schema — NEVER over production). Point a local environment at the restore and run `make test` + `make dbt-test` + row-count comparisons against production (identical counts on core tables). Separately, run the rebuild drill: from raw-lake files only, re-run pipelines into an empty scratch schema and confirm observations match production for two indicators per source, value for value. Time both paths. Write/refresh docs/runbooks/restore.md with the exact tested commands and timings."
2. Founder reads restore.md and confirms they could follow it alone on a bad day.

**VERIFICATION CHECKLIST:**
- [ ] Backup restored to scratch; tests green against the restore; core row counts match production.
- [ ] The raw-only rebuild reproduces matching observations for the sampled indicators (Quality Bar: reproducibility).
- [ ] restore.md contains the tested, timed procedure; production was never touched (scratch-only, proven by the connection strings in the log).

**IF IT GOES WRONG:** Rebuild mismatch vs. production → find which release/transform diverged before closing the step; reproducibility is a core promise, and this is the last cheap moment to repair it.

**COMMIT:** `P4.S11: restore + rebuild drills passed, runbook tested`

---

### P4.S12 — Phase close: the self-running system, verified

**GOAL (plain language):** Verify the whole industrial layer holds together — schedules ran unattended, alerts work, five-plus sources live, budgets met, restore proven — update docs, and close Phase 4.

**WHY IT MATTERS:** A phase is done only when the whole is verified (Master Prompt §3.7). Phase 4's claim is autonomy: the proof is a week of unattended operation, not a green afternoon.

**PREREQUISITES:** P4.S1–S11, plus **at least one full unattended schedule cycle** (let the schedules run for ~a week before this session).
**TIME ESTIMATE:** 60–90 minutes.

**ACTIONS:**
1. Review the unattended week with Claude Code: every scheduled run's outcome from `/status` and ingestion_log — any failure must have alerted (check that it did) and be explained.
2. Drills — instruct:
   > "README fresh-clone drill including Dagster and the review UI; traceability drill on a ministry-PDF number (portal → API → observation → release → staging row + review record → raw PDF + source URL, under a minute, showing the human review step); full suite: make test, dbt-test, Playwright (deployed), load-test smoke."
3. Phase exit checklist below; PROJECT_LOG closes the phase with lessons for Phase 5; **finalize the Phase 5 step file from its draft**; final commit.

**VERIFICATION CHECKLIST (= PHASE 4 EXIT CRITERIA):**
- [ ] One+ week of scheduled runs with zero founder intervention; every failure (if any) alerted and is explained in the log.
- [ ] Five sources live and cited (World Bank, NRB, Census/NSO, IMF, ILO) + the first ministry publication via the review UI.
- [ ] The deliberate-failure alert test still passes (re-run it once).
- [ ] Performance baselines met (P4.S10 doc); restore + rebuild drills passed (P4.S11).
- [ ] Traceability on a PDF-sourced number: under a minute, review step visible.
- [ ] All suites green; all Phase 4 work merged and pushed.
- [ ] PROJECT_LOG closes the phase with lessons-for-Phase-5; the Phase 5 step file is finalized to v1.0.

**IF IT GOES WRONG:** The unattended week had silent failures (no alert) → the phase stays open; alerting gaps are exactly what this phase exists to eliminate.

**COMMIT:** `P4.S12: phase 4 closed — the system runs and reports itself`

---

## After Phase 4

Say to Claude (with the PROJECT_LOG lessons at hand): **"Phase 4 exit criteria met — finalize the Phase 5 step file."** Phase 5 is *Launch & Growth*: the pre-launch audit, privacy-respecting analytics, the feedback program with researchers and journalists, the dataset request queue, the first data stories, and the sustainability plan — the phase where the portal stops being a build project and becomes a living public service.
