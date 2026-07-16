"""The Vercel deploy config must never drift from the project's real dependencies.

`requirements.txt` exists only because Vercel's Python builder cannot read
pyproject.toml. Two files listing the same dependencies is a drift risk: a
version bumped in pyproject.toml but not in requirements.txt would silently
deploy a DIFFERENT API than the one CI tests. These tests lock them together —
the same trick `test_nrb_bfs_layout.py` uses to pin the seed CSV to the
REGISTRY it was generated from.

Offline by design, like the rest of the suite: reads files, touches nothing.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

REQUIREMENTS = Path("requirements.txt")
PYPROJECT = Path("pyproject.toml")
VERCEL_JSON = Path("vercel.json")


def _requirement_lines() -> list[str]:
    """The real requirement lines — blanks and comments stripped."""
    return [
        line.strip()
        for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _pyproject_dependencies() -> list[str]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return [str(dep) for dep in data["project"]["dependencies"]]


def test_requirements_are_exact_copies_of_pyproject_pins() -> None:
    declared = set(_pyproject_dependencies())
    for req in _requirement_lines():
        assert req in declared, (
            f"{req!r} in requirements.txt matches no pyproject.toml dependency"
            " exactly — the deployed API would differ from the tested one"
        )


def test_requirements_cover_everything_the_api_imports() -> None:
    """api/ imports fastapi, psycopg and dotenv at runtime; all must ship."""
    names = {line.split("~=")[0].split("[")[0] for line in _requirement_lines()}
    assert {"fastapi", "psycopg", "python-dotenv"} <= names


def test_vercel_routes_every_url_to_the_real_entrypoint() -> None:
    config = json.loads(VERCEL_JSON.read_text(encoding="utf-8"))
    entrypoints = [build["src"] for build in config["builds"]]
    assert entrypoints == ["api/index.py"], "vercel.json builds an unexpected file"
    assert Path(entrypoints[0]).exists(), "vercel.json points at a file that does not exist"
    # Every URL must reach FastAPI, which does its own routing (/health, /v1/...).
    assert [route["dest"] for route in config["routes"]] == ["api/index.py"]
