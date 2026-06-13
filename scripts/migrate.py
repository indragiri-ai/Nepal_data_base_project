"""Apply and inspect database migrations (P1.S3).

A thin, inspectable wrapper around yoyo-migrations that:
  - loads DATABASE_URL from the local .env (never committed),
  - reads the numbered plain-SQL migrations in db/migrations/,
  - applies them, lists their status, or rolls the most recent one back.

This is the ONLY way the database schema ever changes (Master Prompt §3.2:
migrations only — never hand-edit a live schema).

Usage:
  python scripts/migrate.py apply      # apply all pending migrations
  python scripts/migrate.py list       # show each migration and whether it is applied
  python scripts/migrate.py rollback   # roll back the most recently applied migration
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from yoyo import get_backend, read_migrations

MIGRATIONS_DIR = "db/migrations"
COMMANDS = ("apply", "list", "rollback")


def _database_url() -> str:
    load_dotenv()
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print("FAILURE: DATABASE_URL is empty. Fill in .env (see .env.example).")
        raise SystemExit(1)
    return url


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        print(f"Usage: python scripts/migrate.py [{'|'.join(COMMANDS)}]")
        return 2

    command = sys.argv[1]
    backend = get_backend(_database_url())
    migrations = read_migrations(MIGRATIONS_DIR)

    if not migrations:
        print(f"No migration files found in {MIGRATIONS_DIR}/.")
        return 0

    if command == "list":
        applied_ids = {m.id for m in backend.to_rollback(migrations)}
        print(f"Migrations in {MIGRATIONS_DIR}/:")
        for m in migrations:
            mark = "APPLIED" if m.id in applied_ids else "pending"
            print(f"  [{mark:>7}] {m.id}")
        return 0

    if command == "apply":
        with backend.lock():
            pending = backend.to_apply(migrations)
            if not pending:
                print("Nothing to apply — database is already up to date.")
                return 0
            print(f"Applying {len(pending)} migration(s):")
            for m in pending:
                print(f"  + {m.id}")
            backend.apply_migrations(pending)
        print("SUCCESS: migrations applied.")
        return 0

    # rollback — most recently applied migration only
    with backend.lock():
        applied = backend.to_rollback(migrations)
        if not applied:
            print("Nothing to roll back.")
            return 0
        latest = applied[:1]
        print(f"Rolling back: {latest[0].id}")
        backend.rollback_migrations(latest)
    print("SUCCESS: rolled back one migration.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
