# Runbook — Backup & restore

**Purpose:** what to do when something is lost — the database, the raw lake,
the secrets file, or the whole machine. Written for the founder; every path
below uses commands that already exist in this repo.

**The core insight:** this architecture makes the warehouse largely
*rebuildable*. Code, migrations, and seed CSVs live in git; original source
files live in the raw lake with checksums; the pipelines are idempotent. The
one thing a rebuild cannot recreate is **revision history** (the old vintages
of numbers that sources later revised) — that exists only in the database
itself. That is exactly what backups are for.

---

## What lives where

| Thing | Lives in | Rebuildable? |
|---|---|---|
| Code, migrations, seeds, docs, manifest | Git (GitHub: `indragiri-ai/Nepal_data_base_project`) | Clone it |
| Warehouse (observations, dimensions) | Supabase Postgres | Yes, from code + lake (minus revision history) |
| Raw lake (original xlsx/json payloads) | Supabase Storage bucket `raw-lake` | Mostly — see below |
| Secrets (`.env`) | Local file only, git-ignored | Recreate from `.env.example` + Supabase dashboard |
| Revision history (old vintages) | Supabase Postgres only | **No — only from a backup** |

---

## Scenario 1 — Supabase project is PAUSED (most common)

Symptom: `make check-db` fails with the pooler's "tenant or user not found".
The free tier auto-pauses after ~2–3 weeks idle. **No data is lost.**

1. Log in at supabase.com → project `nepal-data-portal-dev` → **Restore**.
2. Wait ~2 minutes, run `make check-db` — done.

(Happened 2026-07-05; full recovery, everything intact.)

## Scenario 2 — `.env` lost or empty

1. `cp .env.example .env`
2. From the Supabase dashboard: **Connect** → copy the *Session pooler*
   connection string, insert the database password (password manager) →
   paste as `DATABASE_URL`.
3. Project Settings → API: copy the URL and a secret key into
   `SUPABASE_URL` / `SUPABASE_SERVICE_KEY`; `STORAGE_BUCKET=raw-lake`.
4. `make check-db` to confirm.

## Scenario 3 — database lost/corrupted, raw lake intact

Rebuild the warehouse from git + the lake (order matters):

```
make migrate          # schema 0001..000N
make seed             # units, sources, datasets, geography, WB indicators
make load-calendar    # BS<->AD calendar
make seed-periods-ne  # fiscal-year periods
make seed-nrb         # NRB BFS indicators
make ingest-wb        # World Bank data (refetched live)
make nrb-bfs-extract  # NRB data re-parsed from the raw lake
.venv/Scripts/python scripts/nrb_bfs.py status    # spot-check 2 values
.venv/Scripts/python scripts/nrb_bfs.py approve --all
make nrb-bfs-promote
```

Result: current values fully restored with provenance. Revision history is
gone unless you also have a dump (Scenario 5 restores it instead).

## Scenario 4 — raw lake lost

- NRB files: re-run `make nrb-bfs-acquire` after clearing
  `reference/nrb/bfs_manifest.json` — files are re-downloaded from nrb.org.np
  and the manifest's recorded sha256 values let you verify NRB hasn't
  silently altered old files (if a hash differs, that IS a revision — note it
  in the PROJECT_LOG, don't panic).
- World Bank payloads: re-created on the next `make ingest-wb`.
- Risk to accept: NRB could someday remove old files from its site. The lake
  is the hedge; treat it as the primary copy, not a cache.

## Scenario 5 — proper backup & restore (pg_dump)

The master prompt requires a manual dump **before any risky step** (big
migration, mass promotion, geography restructure). Free-tier Supabase has no
downloadable automatic backups, so this is the only true backup path.

One-time setup (Windows): `winget install PostgreSQL.PostgreSQL.17`
(only the client tools are needed).

Backup (creates a single compressed file; store it outside the repo,
e.g. `C:\My_app_AI\backups\`):

```
pg_dump "<DATABASE_URL from .env>" -Fc -f nepal-portal-YYYY-MM-DD.dump
```

Restore into a fresh/empty database:

```
pg_restore --clean --if-exists -d "<DATABASE_URL>" nepal-portal-YYYY-MM-DD.dump
```

This restores EVERYTHING including revision history. After restoring, run
`make check-db` and `make test`, and spot-check one known value via the API
(e.g. GDP growth 2020 = −2.37).

## Scenario 6 — whole machine lost

1. Install Git, Python 3.12, Node LTS, make (`winget install ezwinports.make`).
2. `git clone https://github.com/indragiri-ai/Nepal_data_base_project.git`
3. Follow README "First-time setup", then Scenario 2 for `.env`.
4. Nothing else is needed — the warehouse is still in Supabase, untouched.

---

## Drill status

- Scenario 1 proven live: 2026-07-05.
- Scenario 3 chain proven piecewise: full load executed 2026-07-10
  (59 files, 6,905 observations, release 8).
- Scenario 5 (dump + restore round trip): **not yet drilled** — the master
  prompt schedules this drill for Phase 2's close. Do it against the dev
  database on a quiet day and record the result here.
