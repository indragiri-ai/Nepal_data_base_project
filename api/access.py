"""Bounded responses, and an optional shared request allowance.

Two separate jobs, deliberately:

1. **Always on, no configuration.** Reject absurd query strings, cap how many
   bytes one answer may occupy, put a deadline on the request, and stop the
   response from being cached by anything in between. This costs nothing and
   needs no database.

2. **Only when configured.** A per-caller request allowance shared across
   serverless instances, held in `api_private` (migration 0008) because the
   API has no other shared memory. It is off until `API_CLIENT_HASH_KEY` is
   set, and when it is on, a failure to reserve closes the door rather than
   opening it. The key is required because the allowance is keyed by a hashed
   client address, and an unsalted hash of an IP address is reversible.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import os
from typing import Any, Protocol
from urllib.parse import parse_qsl
from uuid import uuid4

import anyio
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.database import connect, serving_dsn
from api.policy import MAX_RESPONSE_BYTES

log = logging.getLogger(__name__)

MAX_QUERY_BYTES = 4096
MAX_PATH_BYTES = 256
MAX_PARAM_LENGTH = 200
REQUEST_DEADLINE_SECONDS = 20
# `codes` is the one parameter the portal repeats on purpose: one sector page
# asks for many indicators' sparklines in a single request.
REPEATABLE_PARAMS = frozenset({"codes"})


class AccessGuard(Protocol):
    def reserve(self, client: str) -> tuple[str | None, int]: ...
    def finish(self, lease: str, size: int) -> None: ...


def quota_configured() -> bool:
    """True when an operator has set up the shared allowance."""
    return len(os.environ.get("API_CLIENT_HASH_KEY", "")) >= 32


def client_key(scope: Scope) -> str:
    """A stable, non-reversible name for one caller.

    IPv6 callers are grouped by their /64, which is the smallest block a single
    subscriber is normally given: counting each address separately would let one
    machine walk through billions of allowances.
    """
    secret = os.environ["API_CLIENT_HASH_KEY"]
    host = (scope.get("client") or ("unknown", 0))[0]
    # Vercel supplies this header. Never trust client-supplied X-Forwarded-For
    # on local/other deployments; their proxy trust must be configured separately.
    if os.environ.get("VERCEL") == "1":
        headers = dict(scope.get("headers", []))
        host = headers.get(b"x-vercel-forwarded-for", b"").decode("ascii")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # A transport with no IP address (a unix socket, a test client). Group
        # them together rather than refusing to answer at all.
        pass
    else:
        host = (
            str(ipaddress.ip_network(f"{address}/64", strict=False))
            if isinstance(address, ipaddress.IPv6Address)
            else str(address)
        )
    return hmac.new(secret.encode(), host.encode(), hashlib.sha256).hexdigest()


class PostgresGuard:
    """The allowance lives in the database: it is the only state every
    serverless instance of this API can see."""

    def reserve(self, client: str) -> tuple[str | None, int]:
        token = str(uuid4())
        with connect(serving_dsn(), readonly=False) as conn:
            row = conn.execute(
                "SELECT * FROM api_private.reserve_access(%s, %s::uuid)", (client, token)
            ).fetchone()
        if row is None:
            raise RuntimeError("No quota decision")
        return (token if row[0] else None, int(row[1]))

    def finish(self, lease: str, size: int) -> None:
        with connect(serving_dsn(), readonly=False) as conn:
            conn.execute("SELECT api_private.finish_access(%s::uuid, %s)", (lease, size))


class ResponseTooLarge(Exception):
    pass


class AccessMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Health checks and the OpenAPI docs are not data; preflights carry no
        # payload and must reach the CORS layer unimpeded.
        if scope["type"] != "http" or not scope["path"].startswith("/v1"):
            await self.app(scope, receive, send)
            return
        if scope["method"] == "OPTIONS":
            await self.app(scope, receive, send)
            return

        async def error(status: int, detail: str, retry: int = 0) -> None:
            headers = {"Cache-Control": "no-store"}
            if retry:
                headers["Retry-After"] = str(retry)
            await JSONResponse({"detail": detail}, status, headers=headers)(scope, receive, send)

        if not self._request_is_sane(scope):
            await error(414, "Request is too long.")
            return
        duplicate = self._duplicate_or_oversized_param(scope)
        if duplicate:
            await error(422, f"Query parameter '{duplicate}' is too long or repeated.")
            return

        guard: AccessGuard | None = getattr(scope["app"].state, "access_guard", None)
        if guard is None and quota_configured():
            guard = PostgresGuard()

        lease: str | None = None
        if guard is not None:
            try:
                lease, retry = await anyio.to_thread.run_sync(guard.reserve, client_key(scope))
            except Exception:
                log.exception("Request allowance could not be reserved")
                await error(503, "Data access is temporarily unavailable.", 30)
                return
            if lease is None:
                await error(429, "Request allowance reached. Please wait before trying.", retry)
                return

        start: Message | None = None
        body = bytearray()

        async def collect(message: Message) -> None:
            nonlocal start
            if message["type"] == "http.response.start":
                start = message
            elif message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                    raise ResponseTooLarge
                body.extend(chunk)

        failure: tuple[int, str] | None = None
        try:
            with anyio.fail_after(REQUEST_DEADLINE_SECONDS):
                await self.app(scope, receive, collect)
            if start is None:
                raise RuntimeError("The application produced no response")
        except ResponseTooLarge:
            failure = (413, "That answer is too large. Narrow the query and ask again.")
        except Exception:
            log.exception("Request failed inside the access middleware")
            failure = (503, "Data access is temporarily unavailable.")
        finally:
            if lease is not None and guard is not None:
                try:
                    # Settle before releasing any bytes; retain the reservation
                    # if settlement fails. A crashed request's lease expires in
                    # 60s, so a lost settlement costs one slot for one minute.
                    with anyio.CancelScope(shield=True):
                        await anyio.to_thread.run_sync(guard.finish, lease, len(body))
                except Exception:
                    log.exception("Request allowance could not be settled")
                    failure = (503, "Data access is temporarily unavailable.")
        if failure:
            await error(*failure)
            return

        assert start is not None
        headers: list[Any] = [
            (k, v)
            for k, v in start["headers"]
            if k.lower() not in (b"content-length", b"cache-control")
        ]
        headers.extend(
            [
                (b"content-length", str(len(body)).encode()),
                (b"cache-control", b"no-store"),
                (b"x-content-type-options", b"nosniff"),
            ]
        )
        await send({**start, "headers": headers})
        await send({"type": "http.response.body", "body": bytes(body)})

    @staticmethod
    def _request_is_sane(scope: Scope) -> bool:
        return (
            len(scope.get("query_string", b"")) <= MAX_QUERY_BYTES
            and len(scope["path"]) <= MAX_PATH_BYTES
        )

    @staticmethod
    def _duplicate_or_oversized_param(scope: Scope) -> str | None:
        """Name the first parameter that is too long or repeated, if any.

        A repeated parameter is how a caller multiplies the work behind one
        request; FastAPI would silently keep one of them.
        """
        query = scope.get("query_string", b"").decode("utf-8", errors="replace")
        seen: set[str] = set()
        for key, value in parse_qsl(query, keep_blank_values=True):
            if len(value) > MAX_PARAM_LENGTH:
                return key
            if key in seen and key not in REPEATABLE_PARAMS:
                return key
            seen.add(key)
        return None
