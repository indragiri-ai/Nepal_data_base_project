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

.PHONY: setup test lint fmt check-db help

help:  ## Show the available commands
	@echo Nepal Data Portal — available commands:
	@echo   make setup   Install all Python dependencies into the virtual environment
	@echo   make test    Run the test suite (pytest)
	@echo   make lint    Check code quality (ruff lint + mypy type check)
	@echo   make fmt      Auto-format the code (ruff format)
	@echo   make check-db Connect to the database and print its version

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
