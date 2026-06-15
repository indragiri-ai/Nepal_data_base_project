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

## Deploying a live demo (Render)

A `render.yaml` blueprint deploys the whole portal — API + website — as two free
web services anyone can open with a link.

1. Create a free account at [render.com](https://render.com) and connect your GitHub.
2. **New → Blueprint → select this repo.** Render reads `render.yaml` and proposes
   two services: `nepal-data-api` and `nepal-data-web`.
3. When prompted, paste your Supabase connection string into **`DATABASE_URL`**
   (the same value as in your local `.env`). It is the only value you set by hand.
4. **Apply.** Render builds both. The website is auto-wired to the API, so once the
   `nepal-data-web` service is live its `…onrender.com` URL is your public demo link.

Notes: free services sleep after ~15 min idle (first hit is a slow cold start);
the API is read-only and serves your **dev** database; CORS is open (`*`) because
the data is public. To restrict origins later, set `CORS_ALLOW_ORIGINS` on the API
service to a comma-separated list.

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
