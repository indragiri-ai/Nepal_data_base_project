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

**Phase 0 — nothing to run yet.** Accounts and repository are being set up.

From Phase 1 onward, a complete setup sequence will be documented here so that anyone with `.env.example` filled in can reproduce the full system from zero.

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
