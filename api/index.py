"""Vercel serverless entry point for the API.

Vercel's Python builder loads ONE file per function and serves the ASGI `app`
it finds there. It loads that file directly by path, which does not put the
repository root on `sys.path` — so `api.main`'s own `from api.models import ...`
imports would fail. This shim adds the root first, exactly as the scripts in
`scripts/` and `ingestion/nrb/` already do, then re-exports the app unchanged.

The app itself is untouched: `api/main.py` stays the single definition of the
API, and `make api` keeps running it locally through uvicorn. This file adds a
deploy target, not a second version of the API.

Wired up by `vercel.json` at the repo root, which routes every incoming URL
here and lets FastAPI do its own routing (/health, /v1/...).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.main import app  # noqa: E402

__all__ = ["app"]
