"""Check that we can reach the Supabase PostgreSQL database (P1.S2).

Reads DATABASE_URL from the local .env file (never committed), connects, and
prints the server's PostgreSQL version and current time. Prints a clear SUCCESS
or FAILURE message and exits non-zero on failure, so `make check-db` fails
loudly if anything is wrong.
"""

from __future__ import annotations

import os
import sys

import psycopg
from dotenv import load_dotenv


def main() -> int:
    load_dotenv()
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        print(
            "FAILURE: DATABASE_URL is empty. Paste your Supabase connection "
            "string into the .env file (after 'DATABASE_URL=') and try again."
        )
        return 1

    try:
        with psycopg.connect(database_url, connect_timeout=15) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version(), now();")
                row = cur.fetchone()
    except Exception as exc:
        print("FAILURE: could not connect to the database.")
        print(f"  Reason: {exc}")
        return 1

    assert row is not None
    version, server_time = row
    print("SUCCESS: connected to the database.")
    print(f"  PostgreSQL version: {version}")
    print(f"  Server time:        {server_time}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
