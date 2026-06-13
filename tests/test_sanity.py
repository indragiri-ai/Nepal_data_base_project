"""Environment sanity checks — the project's very first test.

These do not test any project logic (there isn't any yet). They confirm the
toolchain set up in P1.S1 is actually in place, so `make test` has something
real to run and `make lint` has a file to check. Real feature tests arrive
from P1.S2 onward.
"""

import sys


def test_python_is_312_or_newer() -> None:
    """The project requires Python 3.12+ (see pyproject.toml)."""
    assert sys.version_info >= (3, 12)


def test_core_dependencies_import() -> None:
    """The pinned runtime dependencies installed and import cleanly."""
    import dotenv  # noqa: F401  (python-dotenv: loads .env secrets)
    import psycopg  # noqa: F401  (PostgreSQL driver)
    import requests  # noqa: F401  (HTTP client for data-source APIs)
    import yoyo  # noqa: F401  (database migrations)
