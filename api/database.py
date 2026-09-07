"""How the API connects: verified TLS, short deadlines, least privilege.

The serving identity is meant to be separate from the ingestion/admin
`DATABASE_URL` (security review 2026-09-06, finding 2). Migration
`0008_api_access.sql` creates that read-only role; until an operator has
created it and set `API_DATABASE_URL`, the API falls back to `DATABASE_URL`
and says so in the log, because a portal that refuses to start is a worse
outcome than one running with the privileges it has always had.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo

log = logging.getLogger(__name__)

SERVING_ROLE = "portal_api"

# Supabase's pooler presents a certificate from Supabase's OWN certificate
# authority ("Supabase Root 2021 CA"), not a public one — `openssl s_client`
# against the pooler shows the issuer. So no public bundle (certifi, the
# system store) can verify it, and `sslmode=verify-full` fails outright
# against every Supabase host until their root certificate is pinned here.
#
# That certificate is published only inside the project dashboard
# (Settings → Database → SSL Configuration → Download certificate), which is
# the trustworthy channel: taking it from the database host itself would mean
# asking the server we cannot yet trust to vouch for itself.
PINNED_CA_PATH = Path(__file__).resolve().parent.parent / "reference/supabase/prod-ca-2021.crt"

# Connection deadlines. The API is a public read service: a query that has not
# answered in five seconds will not become useful by waiting longer, and a
# connection held open past that is a connection the free-tier pooler cannot
# give to anyone else.
CONNECT_TIMEOUT = 5
# 8s, not 5s: the widest honest query the portal makes (13 years of one
# commodity's daily prices, 4,675 rows) was measured at 4.9s end to end on
# 2026-09-07. A 5s ceiling would cut the market-prices chart off some of the
# time — a limit that only fires on real users is worse than no limit.
SESSION_OPTIONS = (
    "-c statement_timeout=8000 -c lock_timeout=1000 "
    "-c idle_in_transaction_session_timeout=10000 -c search_path=public,pg_catalog"
)

_warned = False
_tls_warned = False


def tls_settings() -> tuple[str, str | None]:
    """(sslmode, sslrootcert) — verified identity when we can prove it.

    `verify-full` is the goal (security review 2026-09-06, finding 9): it
    checks *who* answered, where `require` only encrypts the conversation with
    whoever did. It is used the moment a certificate authority is available and
    never guessed at: a verify-full setting with no CA to verify against does
    not fail safe, it simply fails, and the portal goes dark.
    """
    global _tls_warned
    # Deliberately None when nothing is pinned, never a public bundle as a
    # stand-in: libpq documents that `sslmode=require` behaves as `verify-ca`
    # whenever a root certificate IS supplied, so a decorative certifi path
    # here does not sit unused — it fails every connection to Supabase.
    root = os.environ.get("API_SSL_ROOT_CERT") or (
        str(PINNED_CA_PATH) if PINNED_CA_PATH.exists() else None
    )
    mode = os.environ.get("API_SSL_MODE") or ("verify-full" if root else "require")
    if mode != "verify-full" and not _tls_warned:
        _tls_warned = True
        log.warning(
            "Database traffic is encrypted but the server's identity is NOT verified. "
            "Download the SSL certificate from the Supabase dashboard "
            "(Settings -> Database -> SSL Configuration) to %s, and this becomes "
            "verify-full automatically.",
            PINNED_CA_PATH,
        )
    return mode, root


def serving_dsn() -> str:
    """The DSN the API serves from — the restricted role when one exists."""
    global _warned
    dsn = os.environ.get("API_DATABASE_URL", "").strip()
    if dsn:
        user = str(conninfo_to_dict(dsn).get("user") or "")
        # Supabase's pooler appends the project reference to the role name.
        if user.split(".")[0] != SERVING_ROLE:
            raise RuntimeError(f"API_DATABASE_URL must use the restricted {SERVING_ROLE} role")
        return dsn
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        raise RuntimeError("Neither API_DATABASE_URL nor DATABASE_URL is set")
    if not _warned:
        _warned = True
        log.warning(
            "API_DATABASE_URL is not set: serving with the admin DATABASE_URL. "
            "Apply db/migrations/0008_api_access.sql and set API_DATABASE_URL "
            "to the %s role to drop write privileges from the public API.",
            SERVING_ROLE,
        )
    return dsn


def connect(dsn: str, *, readonly: bool = True) -> psycopg.Connection[Any]:
    """Open one short-lived, encrypted, deadline-bounded connection.

    Read-only by default: the public API has no reason to be able to write, and
    a read-only transaction is one more thing standing between a bug and the
    warehouse. `application_name` makes these sessions identifiable, so a
    pipeline's cleanup can tell an API reader from its own abandoned work.
    """
    mode, root = tls_settings()
    settings: dict[str, Any] = {
        "sslmode": mode,
        "connect_timeout": CONNECT_TIMEOUT,
        "application_name": "portal-api",
        "options": SESSION_OPTIONS,
    }
    if root:
        settings["sslrootcert"] = root
    conn = psycopg.connect(make_conninfo(dsn, **settings))
    conn.read_only = readonly
    return conn
