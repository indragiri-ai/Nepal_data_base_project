# Codex session tasks — 2026-08-10 to 2026-08-11

This file records the work completed during the Codex cleanup session. The work
followed `CODEX_FIXES.md` from F1 through F4 and was merged into `master` through
[pull request #2](https://github.com/indragiri-ai/Nepal_data_base_project/pull/2).

## Task file and guardrails

- Added the ordered cleanup backlog and its verification rules in
  `CODEX_FIXES.md`.
- Worked on the stacked branch `fix/f4-kalimati-weekly-refresh`.
- Preserved the project's raw-first, idempotent, revision-safe, API-only, and
  report-never-guess rules.

Commit: `a67adba` — `Codex backlog: the small open items, with their guardrails`

## F1 — ingestion run logging

### Open Data Nepal Kalimati archive

- Added `ingestion_log` records for changed loads, successful no-op checks, and
  raw-archive failures.
- Carried immutable raw-lake references into the log.
- Added offline coverage for all three outcomes.
- Live no-op verification archived both CKAN resources, found 153,494 unchanged
  observations, loaded 0, and still recorded success.
- `/v1/meta` changed from omitting Kalimati to listing it with
  `last_updated=2026-08-10`.

Commit: `918313a` — `fix: Kalimati pipeline records its run in ingestion_log`

### Federal fiscal pipeline

- Added raw-response preservation and `running` to `success` ingestion logging.
- Added successful no-op logging and failed raw-archive logging.
- Added offline tests for changed, no-op, archive-failure, and untouched-byte
  preservation behavior.
- The live source exposed a new, unreviewed `FY2025` value. The loader correctly
  stopped instead of guessing or widening its verified range.

Commit: `8aea32c` — `fix: federal fiscal pipeline records its run in ingestion_log`

### Provincial fiscal pipeline

- Archived every untouched province/year/type Tableau response in one raw
  snapshot.
- Added changed-load, no-op, and raw-archive-failure ingestion logging.
- Added offline tests for the logging outcomes and untouched response bytes.
- The paced live harvest exceeded the 15-minute safety window before opening a
  database connection; no partial run was presented as full freshness.

Commit: `e7611e8` — `fix: provincial fiscal pipeline records its run in ingestion_log`

## F2 — fiscal provenance in API responses

- Verified that all 15 `FISCAL%` warehouse indicators already had
  `origin_source_id=2`.
- Found the actual remaining fault in the API read path: the repository query and
  response builders omitted the indicator source fields.
- Added the source joins and response mapping without changing warehouse source
  records.
- Added a fiscal API regression test.
- Verified locally against the warehouse that `FISCAL_REVENUE_ACTUAL` reports
  `World Bank` as both source and preferred source.

Commit: `8c5aa76` — `fix: fiscal indicators carry their origin source`

## F3 — economy indicator shelves

- Read and classified the unmatched indicator names without inferring meaning
  from codes.
- Added four focused shelves: Tourism & transport, Digital connectivity,
  Research & innovation, and Policy & institutions.
- Preserved all existing founder-facing shelf names and kept `Everything else`
  visible and last.
- Reduced the live unmatched group from 173 to 28 indicators.
- Preserved an exact 647-in/647-out classification with no duplicates or drops.
- Added regressions proving CPIA ratings do not enter Prices and trade series
  with `(% of GDP)` units do not enter Growth.

Commit: `8b21afc` — `web: shelve more economy indicators, shrink "Everything else"`

## F4 — weekly official Kalimati refresh

- Added a weekly Tuesday 02:17 UTC Kalimati job to
  `.github/workflows/ingest.yml`, plus manual `job=kalimati` dispatch.
- Kept the loader's courteous 12-second request spacing and 60/180-second retry
  waits.
- Added non-overlapping execution, a 45-minute timeout, before/after freshness
  reporting, row/runtime reporting, and a labelled GitHub issue alert on failure.
- Added ingestion logging for changed and no-op official-market runs, including
  the raw snapshot reference.
- The first GitHub run received an HTTP-200 tokenless interstitial. The failure
  path opened issue #1 as designed.
- Added retry handling for that transient interstitial and offline tests for the
  retry ladder and terminal failure.
- Configured the four required GitHub Actions secrets from the local environment
  without printing or storing their values in this record.
- Closed issue #1 after the successful recovery run.

Successful run evidence:

- Run: https://github.com/indragiri-ai/Nepal_data_base_project/actions/runs/31443920989
- Harvested: 105,751 commodity-days
- Existing unchanged values: 105,707
- Newly loaded observations: 44, under release 55
- Raw snapshot: 3,015,834 bytes
- Refresh step: 326 seconds; full job: 5 minutes 52 seconds
- Official dataset freshness: not listed to `2026-08-10`

Commits:

- `bd03314` — `ops: weekly Kalimati price refresh`
- `a3968fd` — `fix: retry Kalimati form interstitials`
- `f09f4e0` — `docs: record weekly Kalimati refresh verification`

## Validation and publication

- `make lint`: passed.
- `make test`: 303 passed, with one existing Starlette deprecation warning.
- `cd web && npm run build`: passed.
- Frontend shelf tests: 4 passed.
- Draft PR #2 checks passed for Python, Next.js, and both Vercel previews.
- PR #2 was marked ready and merged into `master` as merge commit `421ca0f`.
- Post-merge CI passed:
  https://github.com/indragiri-ai/Nepal_data_base_project/actions/runs/31492564425
- Both production Vercel deployments reported success.
- The weekly Kalimati cron is now on the default branch and active.

## Status after this session

- Numbered tasks in `CODEX_FIXES.md`: 4.
- Completed: 4.
- Remaining numbered cleanup tasks: 0.
- Separate source follow-ups remain recorded in `docs/PROJECT_LOG.md`: review the
  newly exposed federal `FY2025` data and rerun the full paced provincial fiscal
  harvest with a longer execution window. These were intentionally not guessed
  or treated as completed live verifications.
