# Nepal Data Portal

A single, trustworthy, free portal where anyone — researchers, journalists, students, policymakers, and businesses — can find data about Nepal in one place, in consistent formats, with visualizations, downloads, and a public API.

Every number carries its source, license, definition, and revision history. The portal works across Nepal's two calendar systems (BS and AD) and the 2015 federal boundary restructuring — the two problems that quietly break most Nepali datasets.

## Project documents

| Document | Purpose |
|---|---|
| `docs/nepal-data-portal-blueprint.md` | Architecture: data model, harmonization rules, technology decisions |
| `docs/nepal-data-portal-master-prompt.md` | Engineering standards, step system, phase map |
| `docs/steps/phase-0-steps.md` | Phase 0 step-by-step guide (accounts, tools, repo) |
| `docs/steps/phase-1-steps.md` | Phase 1 step-by-step guide (walking skeleton) |
| `docs/PROJECT_LOG.md` | Dated diary of every step completed |

## Repository structure

```
nepal-data-portal/
├── docs/                  # blueprint, master prompt, step files, PROJECT_LOG, decisions, runbooks
├── ingestion/             # one folder per source: worldbank/ imf/ ilo/ nrb/ nso/ ministries/
├── transform/             # dbt project and Python transforms
├── db/                    # migrations/ (numbered SQL) and seeds/ (reference data)
├── api/                   # FastAPI application
├── web/                   # Next.js application
├── reference/             # calendar table, geography master, GeoJSON boundaries
├── scripts/               # one-off utilities
├── tests/                 # pytest suites
├── .env.example           # every required variable with placeholder values
└── Makefile               # one-command entry points (added in Phase 1)
```

## How to run (updated each phase)

This section grows with each phase so that anyone with `.env.example` filled in can
reproduce the system from zero.

### Prerequisites
- **Python 3.12+** — the data/backend language.
- **Node.js LTS** — the website (used from Phase 1's frontend step onward).
- **make** — runs the one-command shortcuts below. (On Windows it isn't built in;
  install once with `winget install ezwinports.make`.)

### First-time setup
```
py -3.12 -m venv .venv      # create the isolated Python environment (once)
make setup                   # install all pinned dependencies into it
cp .env.example .env         # then open .env and fill in your real values
```
`.env` holds your secrets (database URL, Supabase keys) and is git-ignored — it
is never committed. Every variable the project needs is listed in `.env.example`
with a placeholder; copy it to `.env` and paste your real values from the
Supabase dashboard. Nothing below (`make migrate`, `make seed`, `make ingest-wb`)
works until `.env` has a valid `DATABASE_URL`.

### Everyday commands
| Command | What it does |
|---|---|
| `make setup` | Install/update all Python dependencies |
| `make test`  | Run the test suite (pytest) |
| `make lint`  | Check code quality (ruff lint + mypy type check) |
| `make fmt`   | Auto-format the code (ruff) |

More commands (`make check-db`, `make migrate`, `make seed`, `make ingest-wb`,
`make api`, `make web`) are added as later Phase 1 steps build each layer.

### Seeing the portal (the full slice, end to end)
The website reads the API; the API reads the warehouse. Run them together:
```
make migrate        # create the schema (once)
make seed           # load reference data: Nepal, years, units, 20 indicators (once)
make load-calendar  # load the BS<->AD day-level calendar reference (once)
make seed-periods-ne # add Nepali fiscal-year periods (needs load-calendar first)
make ingest-wb      # fetch the World Bank data into the warehouse (once)
make web-setup      # install the website's Node dependencies (once)
```
Then, in two terminals:
```
make api            # terminal 1 — API at http://localhost:8000 (docs at /docs)
make web            # terminal 2 — website at http://localhost:3000
```
Open <http://localhost:3000>, pick an indicator (e.g. "GDP growth (annual %)"),
and you should see an interactive, source-cited chart. The website never touches
the database directly — only the API.

### NRB banking statistics (monthly time series + dashboard)

Nepal Rastra Bank's "Banking and Financial Statistics — Monthly" Excel files
(2021 onward) become monthly time series through the staging-and-review flow —
extracted rows wait in a holding table until a human approves them:
```
make seed-nrb          # register the 35 banking indicators (once, after make seed)
make nrb-bfs-acquire   # download new monthly Excel files into the raw lake
make nrb-bfs-extract   # parse table C4 into the staging table
make nrb-bfs-status    # see what awaits review, with a spot-check sample
.venv/Scripts/python scripts/nrb_bfs.py approve --all    # after eyeballing the sample
make nrb-bfs-promote   # quality-gate + load into the warehouse
```
Then open <http://localhost:3000/banking> — the banking sector dashboard:
every indicator by bank class, with month-over-month and year-over-year views.
Each new month NRB publishes, re-run acquire → extract → approve → promote;
every command is idempotent.

## Deploying a live demo (Vercel — current home)

The portal is live on **Vercel's free (Hobby) plan**, which — unlike Render's
free tier — does **not** sleep and **cannot** bill you (exceeding a limit pauses
the feature rather than charging). It is deployed as **two Vercel projects from
this one repo**:

- **API** — project `nepal-data-base-project`, built from the repo root via
  `vercel.json` (`@vercel/python`, entrypoint `api/index.py`). Public URL:
  <https://nepal-data-base-project.vercel.app>. Needs two env vars in the Vercel
  dashboard: `DATABASE_URL` (Supabase **pooler** string — see below) and
  `CORS_ALLOW_ORIGINS=*`.
- **Website** — project `nepal-data-base-project-7oru`, **Root Directory set to
  `web`** so Vercel builds the Next.js app (also pinned via `web/vercel.json`).
  One env var: `NEXT_PUBLIC_API_BASE` = the API URL above (inlined at build time).
  Public URL: <https://nepal-data-base-project-7oru.vercel.app>.

Two hard-won gotchas (both cost a debug session):

1. **`DATABASE_URL` must use the Supabase *pooler* host**
   (`aws-1-…​.pooler.supabase.com:5432`, username `postgres.<project-ref>`), not
   the direct `db.<ref>.supabase.co` host — the direct host is IPv6-only and
   Vercel (like Render) can only reach IPv4. Importing the local `.env`, which
   uses the direct host, deploys a broken value. Copy the *working* pooler string
   (e.g. from the Render service's env, or Supabase → Database → Connection string).
2. **`CORS_ALLOW_ORIGINS=*` must be set on the API**, or the browser blocks the
   website's requests (the API defaults to `localhost` only). Changing any env var
   requires a redeploy — pushing a commit to `master` triggers a fresh build.

A **daily keep-alive** (`.github/workflows/keep-alive.yml`) pings the API so the
free-tier Supabase DB doesn't auto-pause; a non-200 fails the run and emails you.

**Scheduled ingestion** (`.github/workflows/ingest.yml`) keeps the data fresh
automatically: World Bank weekly (Sundays), NRB monthly (the 20th). A failed run
turns red and emails you — that's the staleness alarm. The NRB job only stages
new files; you still review and `make nrb-bfs-promote` locally (human-made Excel
goes through review). It needs four **Actions secrets** (Settings → Secrets and
variables → Actions), copied from your local `.env`: `DATABASE_URL` (the pooler
host), `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `STORAGE_BUCKET`. Run either
pipeline on demand from the Actions tab ("Run workflow"). GitHub disables cron
workflows after ~60 days of no repo activity — any push to `master` resets that
timer. The site footer shows "Data last updated …" from the API's `/v1/meta`.

### Legacy: Render blueprint

`render.yaml` still deploys the same portal to Render (`nepal-data-api` /
`nepal-data-web`). It works but the free tier sleeps after ~15 min idle (slow
cold start), which is why the live link moved to Vercel. Kept as a fallback.

## Data sources (planned, in integration order)

1. World Bank Open Data API (Nepal WDI indicators)
2. IMF SDMX API
3. ILOSTAT (labor statistics)
4. NRB — Nepal Rastra Bank (Excel/PDF publications)
5. NSO/CBS — Census 2011 & 2021, surveys
6. Ministry and departmental publications (mostly PDF)

## Standards

All work follows `docs/nepal-data-portal-master-prompt.md`. Key rules:
- Secrets in `.env` only — never committed.
- Schema changes only through numbered migrations in `db/migrations/`.
- Every pipeline writes raw data before parsing.
- Every commit references its step: `P1.S4: create observations fact table`.
