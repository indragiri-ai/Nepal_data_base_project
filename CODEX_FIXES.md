# CODEX_FIXES — the small open items, in order

**Goal:** close the small, well-scoped items left behind by finished sources.
None of these is new capability; every one is a gap in something already built.
**One task per session.** Work top to bottom — F1 first, it is the most valuable
and has an exact precedent to copy.

This file is written for the **OpenAI Codex CLI**. Read `CLAUDE.md` first — its
non-negotiable rules override everything here. `CODEX_TASKS.md` in this same
folder is a **different, already-completed** job (the census load); do not work
from it.

---

## Non-negotiables (from CLAUDE.md — do not relearn the hard way)

1. **Never guess.** If a fact cannot be verified from the code, the database or
   the source, **report it — do not invent it.** A parser meeting an unknown
   label fails loudly.
2. **UTF-8 stdout.** Every entrypoint calls `configure_stdout_utf8()` from
   `ingestion/common/io_utf8.py` first. The Windows console is cp1252 and dies
   on Devanagari and em-dashes otherwise.
3. **Everything idempotent.** Re-running anything must not duplicate.
4. **Revisions never overwrite.** New values insert under a new release; the
   `is_latest` trigger demotes old rows. Nothing is deleted.
5. **The browser talks only to the API**, never the database.
6. **The three gates must be green before any commit:**
   `make lint` (ruff + mypy) · `make test` (pytest, offline) ·
   `cd web && npm run build`.
7. **Supabase free tier:** batch with `executemany` on short-lived connections.
   A crashed run leaves an `idle in transaction` zombie that blocks the next
   one; the cleaner only kills sessions idle **over five minutes** — do not
   lower that, a slow healthy run looks identical to a corpse.

**Verify before you fix.** Every task below starts with a check. If the check
says the problem is already gone, **stop, say so, and move to the next task** —
do not change working code to match a stale note.

---

## Working method (applies to every task)

- Work on a branch: `git switch -c fix/<task-id>`. **One agent on the repo at a
  time** — if Claude Code is also working, take turns or stay on your branch.
- Commit after each task so work is never lost.
- Tests are **offline by design**. Anything needing the live warehouse is a
  separate manual verification step, called out per task. If `DATABASE_URL` is
  not set, do the code + offline tests, and **write down what still needs a live
  run** rather than skipping it silently.
- End a session by adding a row to `docs/PROJECT_LOG.md` (**newest at top**),
  matching the existing columns: Date · Step · What was done · Evidence · Next.

---

## F1 — Pipelines that never tell the portal they ran (highest value)

**The problem.** `/v1/meta` drives the site's "Data last updated" line and its
dataset list, and it reads the **`ingestion_log` table — not `observations`**.
A pipeline that loads data without writing a log row leaves the portal telling
visitors the data is older than it is, and omits that source from the freshness
list entirely. This exact bug was found on the live site on 2026-08-09 for the
Election Commission and fixed there; the same fix was never applied elsewhere.

**Verified on 2026-08-10:** these already write `ingestion_log` and need no work
— `ingestion/election/ecn_pipeline.py`, `ingestion/worldbank/pipeline.py`,
`ingestion/nso/census_pipeline.py`, `census_local_units.py`, `census_bulk.py`,
`census_shape_a.py`, and `scripts/nrb_bfs.py` (which does `running` → `success`,
plus a `failed` row written on a *fresh connection*, because the failure may be
a dead connection — worth reading, it is the most defensive of the set).

These do **not**:

| File | Dataset it loads |
|---|---|
| `ingestion/opendatanepal/kalimati_pipeline.py` | Kalimati daily food prices |
| `ingestion/worldbank/fiscal_pipeline.py` | Federal fiscal series |
| `ingestion/worldbank/fiscal_provincial.py` | Provincial fiscal series |

One secondary check while you are in there: of the pipelines that *do* log, only
`ecn_pipeline.py` is known to write a **`success` row when a re-run changes
nothing**. If another one silently returns early on a no-op, it has the same
"fresh data looks stale" bug in a milder form. **Report what you find; fix only
`ecn_pipeline.py`'s three siblings in the table above** — widening the blast
radius mid-task is how a small fix becomes a regression.

**The reference implementation to copy is `ingestion/election/ecn_pipeline.py`,
lines ~915–985.** Read it before writing anything. It records four outcomes:

- a `'running'` row inserted with the `release_id` at the start of the write,
  updated to `'success'` at the end with `rows_in` / `rows_loaded` /
  `rows_rejected`;
- a `'failed'` row if the raw archive fails, so a load that never happened is
  not silently absent;
- **a `'success'` row when a re-run changes nothing.** This one matters and is
  deliberate: a healthy no-op run is still evidence the source was checked
  today. Logging only on change would make fresh data look stale. Copy the
  comment explaining why, do not just copy the code.

**Do this per pipeline, one commit each.** Do not refactor the four into a
shared helper on the way — they differ in how they handle releases, and a
shared abstraction written blind is how this kind of fix breaks a working
loader. If after reading all four a helper is *obviously* right, say so in the
PROJECT_LOG entry and leave it for a human to approve.

**Verification.**
- Offline: a test per pipeline asserting a log row is written on a load, on a
  no-op re-run, and on a raw-archive failure. Follow the existing test style in
  `tests/test_ecn_pipeline.py`.
- Live (needs `DATABASE_URL`): re-run each pipeline. It should load **0 rows**
  (they are all idempotent and already loaded) and still write a `'success'`
  log row. Then call `/v1/meta` and confirm the dataset now appears with a
  current date. **Report the before and after dates.**

**Commit:** `fix: <source> pipeline records its run in ingestion_log`

---

## F2 — `indicator.source` comes back null for fiscal indicators

**The problem.** Recorded in `docs/PROJECT_LOG.md` on 2026-08-06:
`/v1/data` reported `indicator.source = null` for the fiscal indicators,
federal ones included. `api/repository.py` reads it via
`LEFT JOIN sources os ON os.id = i.origin_source_id` (~line 274), so a null
means `indicators.origin_source_id` was never set for those rows.

**Check first — this note is four days old and may already be fixed.**
`ingestion/worldbank/fiscal_pipeline.py` *does* reference `origin_source_id`;
`fiscal_provincial.py` does not. So the federal half may be resolved and the
provincial half not. Query the warehouse:

```sql
SELECT code, origin_source_id FROM indicators WHERE code LIKE 'FISCAL%' ORDER BY code;
```

- If every row has a source id, **the task is done** — say so and stop.
- If only provincial rows are null, fix only those.

**The fix** is to set `origin_source_id` the way the other loaders do (see
`ingestion/election/ecn_pipeline.py` and `scripts/seed.py`). The source is the
**World Bank** as compiler — the Nepal Fiscal Dashboard is a compilation of
Ministry of Finance, FCGO and Nepal Rastra Bank records, and that distinction is
already recorded in `reference/wb-fiscal/PROVENANCE.md`. Read it and match what
is written there. **Do not invent a new source row** — reuse the existing one.

**Verification.** Offline test that the API model carries a non-null source for
a fiscal indicator. Live: `GET /v1/data?indicator=FISCAL_REVENUE_ACTUAL&geo=NP`
and confirm `indicator.source` names the publisher.

**Commit:** `fix: fiscal indicators carry their origin source`

---

## F3 — "Everything else" holds 164 of the 647 economy indicators

**The problem.** `/economy` shelves its indicators into themes defined in
`web/lib/sectors.ts` (`ECONOMY_THEMES`, ~line 55). Anything unmatched lands in a
visible **"Everything else"** shelf (`OTHER_THEME`, ~line 305), placed last and
deliberately never hidden — a growing pile there is the signal the themes need
work. It currently holds **164** items. Current shelves: Prices 33, Government
finance 86, Trade 98, External 81, Money 36, Poverty 18, Business 62, Growth 69.

**The task:** read the 164 unmatched names and add or widen themes so that pile
shrinks meaningfully. This is a judgment task, so the guardrails matter more
than the target number.

**Three traps already paid for once — read `shelveIndicators` (~line 337) and
the 2026-08-06 PROJECT_LOG entry before editing:**

1. **Match at word starts, not substrings.** `cpi` once matched the World
   Bank's *CPIA policy ratings* and filed them under prices.
2. **Strip the bracketed unit before matching.** `(% of GDP)` once dragged 106
   trade and credit series onto the national-accounts shelf, because the match
   hit the *denominator*, not the subject.
3. **The broad shelf runs last.** Order in `ECONOMY_THEMES` is precedence.

**Hard constraints.**
- **The total must not change.** 647 in, 647 out — no indicator may be dropped
  or land on two shelves. Assert this in a test.
- **Do not rename existing shelves** — the founder has seen these names.
- **Do not delete "Everything else"** or hide it. If it ends at 40, that is a
  good outcome honestly displayed.
- Every indicator you shelve must belong there on its **name**, not on a guess
  about what the code means.

**Verification.** A test asserting the round trip (every input indicator appears
exactly once across all shelves) and asserting the known traps stay fixed — a
CPIA rating is not in Prices, a "(% of GDP)" trade series is not in Growth.
`cd web && npm run build` green. Then look at the page in a browser and report
the new shelf counts.

**Commit:** `web: shelve more economy indicators, shrink "Everything else"`

---

## F4 — Kalimati prices are frozen at the 8 August snapshot

**The problem.** Kalimati is the portal's most relatable dataset — a decade of
daily food prices — and it has no refresh, so it ages a day every day. The
harvest channel already exists and works: `ingestion/kalimati/price_history.py`
(the market board's own site, a different channel from the Open Data Nepal
archive), driven by `ingestion/opendatanepal/kalimati_pipeline.py`.

**Do F1 first** — a scheduled job whose loads are invisible to `/v1/meta` is
exactly the bug F1 fixes, and this workflow is what would make it obvious.

**The task:** a scheduled GitHub Actions workflow that refreshes Kalimati
weekly. Model it on the two that already exist and work:
`.github/workflows/ingest.yml` (a scheduled ingest with database secrets) and
`.github/workflows/wb-fiscal-watch.yml` (a scheduled check that opens a labelled
issue rather than only turning red — a red run months later is easy to miss).

**Requirements.**
- Weekly, not daily. The board publishes daily, but this is a free tier and a
  polite guest — weekly is enough to stop the data ageing visibly.
- **Be a good guest to a government server.** The Election Commission harvest
  died at request 650 of 753 when its server hung up; the fix was "ask less, not
  harder" — retry a dropped connection on the same 30/90/180s ladder as a rate
  limit, and rest between batches. Whatever `price_history.py` already does
  here, do not make it more aggressive.
- **A failed run must be loud** — open an issue, the way the fiscal watcher
  does. Silence must never look like success.
- The load is idempotent already, so a re-run that finds nothing new must load
  0 and still log a successful run (that is F1's behaviour — this is why F1
  comes first).

**Verification.** Trigger the workflow manually (`workflow_dispatch`) once and
report: rows loaded, the `/v1/meta` date before and after, and the run time.
Then confirm the schedule is registered.

**Commit:** `ops: weekly Kalimati price refresh`

---

## Do NOT do these (they are not Codex tasks)

These are open, and they are deliberately staying open. Do not "helpfully" close
them — each one would require inventing something a human must decide.

- **Nepali names (`name_ne`) for the 753 municipalities and all indicators.**
  Missing, so Nepali search reaches provinces and districts only. Filling it is
  **human-curated seed work** (rule 4). Machine transliteration is forbidden.
- **The chandrabindu / anusvara spelling question.** Kathmandu is stored
  `काठमाडौँ`; a user typing `काठमाडौं` gets nothing. Declaring ँ and ं
  interchangeable is a judgment about the Nepali language, not a code change.
  **It needs the founder's decision.**
- **English names for the ~123 political parties.** The Commission publishes
  English for only a handful. Transliterating the rest ourselves would invent
  official-looking names no source ever published.
- **The 110 proportional seats.** They live in a separate ECN notice as a PDF,
  which means staging + human review — a step of its own, not a small fix.
- **Deputy / ward-chair / ward-member races per municipality.** The same 753
  files already carry them and it needs only a wider parse, but it is a data
  load with its own verification, not a cleanup.
- **The unanswered World Bank question** about what the federal aggregate
  revenue row represents. Until they answer, the revenue category breakdowns
  stay withheld. Do not publish them, and do not derive them.

---

## Suggested prompt to start a task

> Read `CLAUDE.md` and `CODEX_FIXES.md`. Do task **F1** only, for
> `ingestion/opendatanepal/kalimati_pipeline.py`, following the reference
> implementation in `ingestion/election/ecn_pipeline.py` lines 915–985 exactly.
> Start with the verification step described in the task. Run `make lint`,
> `make test`, and `cd web && npm run build` before committing. If anything is
> ambiguous, stop and leave a note rather than guessing.
