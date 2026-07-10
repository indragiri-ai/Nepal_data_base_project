# Nepal Data Portal — session orientation

One trustworthy, free portal for data about Nepal: ingestion pipelines →
Postgres warehouse (Supabase) → FastAPI (`api/`) → Next.js site (`web/`).
Python 3.12 in `.venv`; commands run through `make` (see README for the list).

## Read before building

- `docs/nepal-data-portal-master-prompt.md` — engineering standards, the
  step system, phase map. **The session protocol in §6 governs how work
  proceeds**; steps live in `docs/steps/phase-N-steps.md`.
- `docs/nepal-data-portal-blueprint.md` — data model and harmonization rules.
- `docs/PROJECT_LOG.md` — the diary. Newest entry = current state + next step.
  **Every session ends by adding an entry here.**
- `docs/decisions/` — recorded decisions (0003: sectors organize the portal,
  sources are provenance only).
- `docs/runbooks/adding-a-data-source.md` — the checklist for any new source.

## Non-negotiable rules (hard-won; do not relearn these)

1. **Never guess.** Unverifiable data, dates, codes, or mappings are reported,
   not invented. A parser that meets an unknown label fails loudly.
2. **UTF-8 stdout.** Every entrypoint calls `configure_stdout_utf8()` from
   `ingestion/common/io_utf8.py` — the Windows console is cp1252 and crashes
   on Devanagari otherwise.
3. **Raw first.** Store the untouched payload in the raw lake (hashed,
   immutable) BEFORE parsing. Human-made files (Excel/PDF) go through
   staging + human review before promotion; clean APIs may load directly.
4. **Reference data is seeded from CSVs in `db/seeds/`** (curated by a human,
   upserted idempotently) — never created on the fly by a pipeline.
5. **Revisions never overwrite.** New values insert under a new release; the
   `is_latest` trigger demotes old rows. Nothing is deleted.
6. **Everything idempotent.** Re-running any pipeline must not duplicate.
7. **The browser talks only to the API**, never the database.
8. **Supabase free tier quirks:** it drops connections under sustained
   row-by-row writes (batch with `executemany`, short-lived connections) and
   a crashed run leaves an `idle in transaction` zombie that lock-blocks the
   next run (pipelines clear their own stale sessions pre-flight). The dev
   project auto-pauses after ~2–3 weeks idle — resume it in the dashboard.

## Verification gates (all must be green before a step closes)

`make lint` (ruff + mypy) · `make test` (pytest, offline by design) ·
`cd web && npm run build` — CI runs the same three on every push.

## Deployment

`render.yaml` blueprint → Render (`nepal-data-web` / `nepal-data-api`,
free tier, sleeps when idle). Deploys happen by pushing to `master` on
GitHub (`indragiri-ai/Nepal_data_base_project`).

## The founder

Non-technical: announce commands before running them, explain in plain
language, and treat declined permission prompts as a "no", not an error.
