"""Operational scripts (seeding, migrations, catalogue curation).

This file makes `scripts` a real package so modules can import each other by a
single unambiguous name — `scripts.wb_catalog` — rather than mypy seeing the
same file as both `wb_catalog` and `scripts.wb_catalog`. The scripts are still
runnable directly (`python scripts/seed.py`) and as modules
(`python -m scripts.wb_catalog`).
"""
