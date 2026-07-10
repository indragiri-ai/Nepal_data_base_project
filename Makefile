# Nepal Data Portal — one-command entry points.
# Run these as `make setup`, `make test`, `make lint`, `make fmt`.
# Each target wraps a longer command so you never have to remember the details.

# --- Locate the virtual environment's tools on either Windows or macOS/Linux ---
ifeq ($(OS),Windows_NT)
    VENV_BIN := .venv/Scripts
else
    VENV_BIN := .venv/bin
endif

PY    := $(VENV_BIN)/python
RUFF  := $(VENV_BIN)/ruff
MYPY  := $(VENV_BIN)/mypy
PYTEST := $(VENV_BIN)/pytest

.PHONY: setup test lint fmt check-db migrate migrate-status migrate-rollback seed load-calendar seed-periods-ne ingest-wb seed-nrb nrb-bfs-acquire nrb-bfs-extract nrb-bfs-status nrb-bfs-promote api web web-setup help

help:  ## Show the available commands
	@echo Nepal Data Portal — available commands:
	@echo   make setup   Install all Python dependencies into the virtual environment
	@echo   make test    Run the test suite (pytest)
	@echo   make lint    Check code quality (ruff lint + mypy type check)
	@echo   make fmt      Auto-format the code (ruff format)
	@echo   make check-db Connect to the database and print its version
	@echo   make migrate        Apply all pending database migrations
	@echo   make migrate-status Show which migrations are applied

setup:  ## Install all dependencies (runtime + dev) into the virtual environment
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dev]"

test:  ## Run the test suite
	$(PYTEST)

lint:  ## Check code quality: ruff lint then mypy type check
	$(RUFF) check .
	$(MYPY) .

fmt:  ## Auto-format all code with ruff
	$(RUFF) format .
	$(RUFF) check --fix .

check-db:  ## Connect to the database and print its version (verifies .env)
	$(PY) scripts/check_db.py

migrate:  ## Apply all pending database migrations
	$(PY) scripts/migrate.py apply

migrate-status:  ## Show each migration and whether it is applied
	$(PY) scripts/migrate.py list

migrate-rollback:  ## Roll back the most recently applied migration
	$(PY) scripts/migrate.py rollback

seed:  ## Load reference data (geography, periods, units, World Bank indicators)
	$(PY) scripts/seed.py

load-calendar:  ## Load the BS<->AD day-level calendar reference (idempotent)
	$(PY) scripts/load_bs_calendar.py

seed-periods-ne:  ## Seed Nepali fiscal-year time periods from bs_calendar (idempotent)
	$(PY) scripts/seed_periods_ne.py

ingest-wb:  ## Fetch World Bank indicators for Nepal into the warehouse (raw-first, idempotent)
	$(PY) -m ingestion.worldbank.pipeline

seed-nrb:  ## Seed the 35 NRB Banking & Financial Statistics indicators (idempotent)
	$(PY) scripts/seed_nrb.py

nrb-bfs-acquire:  ## Download new NRB BFS monthly Excel files into the raw lake (idempotent)
	$(PY) -m ingestion.nrb.bfs_acquire

nrb-bfs-extract:  ## Parse acquired BFS files (table C4) into the staging table (idempotent)
	$(PY) -m ingestion.nrb.bfs_extract

nrb-bfs-status:  ## Show the BFS staging review queue with a spot-check sample
	$(PY) scripts/nrb_bfs.py status

nrb-bfs-promote:  ## Promote APPROVED staging rows into observations (quality-gated)
	$(PY) scripts/nrb_bfs.py promote
# approve/reject take arguments — run directly, e.g.:
#   .venv/Scripts/python scripts/nrb_bfs.py approve --month 2083-01   (or --all)
#   .venv/Scripts/python scripts/nrb_bfs.py reject  --month 2083-01 --note "why"

api:  ## Run the read-only API locally at http://localhost:8000 (docs at /docs)
	$(PY) -m uvicorn api.main:app --reload --port 8000

web-setup:  ## Install the website's Node dependencies (run once)
	cd web && npm install

web:  ## Run the website locally at http://localhost:3000 (needs `make api` running too)
	cd web && npm run dev
