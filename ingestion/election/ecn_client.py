"""A plain-HTTP client for the Election Commission's results portal (ECN.S1).

WHAT THIS TALKS TO
------------------
`https://result.election.gov.np` is an ASP.NET application whose pages are
shells: every number a visitor sees arrives afterwards from ONE endpoint,

    /Handlers/SecureJson.ashx?file=<path under JSONFiles/>

which returns ordinary JSON. So the portal is machine-readable end to end and
this project never needs a browser to read it — which matters, because a
pipeline that depends on a browser breaks the moment the page layout moves.

THE FOUR THINGS THE HANDLER DEMANDS
-----------------------------------
Getting a 200 out of it took four ingredients, each found by elimination.
Miss any one and the answer is `403 Forbidden` — an HTML error page, not JSON,
so a naive caller sees "success" and parses garbage:

1. a **session**: GET the landing page first, which sets an `ASP.NET_SessionId`
   cookie and a `CsrfToken` cookie;
2. the **CSRF header** `X-CSRF-Token`, echoing that cookie's value — the site's
   own JavaScript reads it straight back out of `document.cookie`;
3. a **browser User-Agent** — curl's default UA is refused;
4. a **Referer** on the portal's own host.

None of this is a security control we are defeating: the token is handed to
every anonymous visitor, unprompted, and the pages are public. It is a
same-origin nuisance filter, and we behave exactly like the site's own page.

BEING A GOOD GUEST — AND THE 429 THAT TAUGHT US
-----------------------------------------------
One government server, one visitor. Requests are sequential with a pause
between them, and the whole inventory is a few hundred files, fetched once —
this is not a live feed and nothing here should ever be polled during an
election count (see the sensitivity policy in
`docs/steps/onboard-election-commission.md`).

The portal enforces this itself. At a 0.8s pause the first reconnaissance run
was throttled after ~70 requests: fifteen consecutive `429 Too Many Requests`,
then service resumed. That is the source telling us the rate, so the pause was
raised and a backoff added.

The damage a 429 does is worse than a delay, which is why it is handled here
and not left to callers: a throttled response looks exactly like a missing
file (non-JSON, an HTML body), so a naive caller records "this district has no
data" and then reports that the district totals do not reconcile. The first run
did precisely that. **A 429 is retried, and if it persists it is raised** —
never returned as an absence.

THREE TRAPS WORTH KNOWING
-------------------------
* **BOM.** Several files are UTF-8 *with* a byte-order mark, which
  `json.loads` rejects outright. Every payload is decoded `utf-8-sig`.
* **A 200 that is not JSON.** The 403 page comes back with status 200 in some
  paths and always with `Content-Type: text/html`. `fetch_json` therefore
  insists on a JSON content type before it will parse, and raises otherwise
  rather than returning something plausible-looking.
* **429 is not 404.** See above. Absence has to be proved, not inferred from a
  failure to answer.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import requests

BASE_URL = "https://result.election.gov.np"
HANDLER_PATH = "/Handlers/SecureJson.ashx"

# A real browser UA. The handler refuses curl/python defaults with 403; this is
# not evasion, it is the minimum needed to be served the same public page a
# visitor gets.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# One government server, sequential requests. 0.8s was demonstrably too fast —
# the portal returned 429 after ~70 requests. Do not lower this.
REQUEST_PAUSE_S = 2.0

# When throttled, wait progressively longer. The observed 429 window lasted
# roughly a dozen requests, so the first wait is already generous; the point is
# to stop asking, not to ask more cleverly.
THROTTLE_BACKOFF_S = (30.0, 90.0, 180.0)

REQUEST_TIMEOUT_S = 60

HTTP_TOO_MANY_REQUESTS = 429


class EcnError(Exception):
    """The ECN portal did not answer in the shape we require."""


class EcnThrottled(EcnError):
    """The portal rate-limited us and kept doing so through every backoff.

    Deliberately its own type: a caller enumerating files must be able to tell
    "the portal would not answer" from "this file does not exist", because
    treating the first as the second silently deletes real data.
    """


@dataclass(frozen=True)
class Fetched:
    """One raw response, kept as bytes so the raw lake stores the real payload."""

    file_path: str
    url: str
    status_code: int
    content_type: str
    content: bytes

    @property
    def is_json(self) -> bool:
        return self.status_code == 200 and "json" in self.content_type.lower()


class EcnClient:
    """Sequential, polite reader of the ECN results portal."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        session: requests.Session | None = None,
        pause_s: float = REQUEST_PAUSE_S,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.pause_s = pause_s
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT})
        self._token: str | None = None

    # -- session -----------------------------------------------------------
    def open_session(self) -> str:
        """Fetch the landing page to collect the CSRF cookie. Returns the token."""
        resp = self._session.get(self.base_url + "/", timeout=REQUEST_TIMEOUT_S)
        if resp.status_code != 200:
            raise EcnError(f"landing page returned HTTP {resp.status_code}")
        token = self._session.cookies.get("CsrfToken")
        if not token:
            # If the portal ever stops issuing the cookie, every later request
            # would 403 with no clue why. Fail here, where the cause is obvious.
            raise EcnError(
                "no CsrfToken cookie was set by the landing page — the portal's "
                "session handling has changed; re-run the ECN.S1 spike"
            )
        self._token = token
        return token

    def _ensure_token(self) -> str:
        if self._token is None:
            return self.open_session()
        return self._token

    # -- fetching ----------------------------------------------------------
    def fetch(self, file_path: str, referer: str | None = None) -> Fetched:
        """GET one file through the handler.

        A 404 is returned normally — the caller is often probing whether a path
        exists at all, and its absence is the answer. A 429 is NOT: it is
        retried with backoff and finally raised, because an unanswered request
        is not evidence of an empty file.
        """
        token = self._ensure_token()
        url = f"{self.base_url}{HANDLER_PATH}?file={file_path}"
        headers = {"X-CSRF-Token": token, "Referer": referer or (self.base_url + "/")}

        for attempt, backoff in enumerate((0.0, *THROTTLE_BACKOFF_S)):
            if backoff:
                print(
                    f"  throttled by the portal (429) — waiting {backoff:.0f}s "
                    f"before retry {attempt} of {len(THROTTLE_BACKOFF_S)}: {file_path}"
                )
                time.sleep(backoff)
            resp = self._session.get(url, headers=headers, timeout=REQUEST_TIMEOUT_S)
            time.sleep(self.pause_s)
            if resp.status_code != HTTP_TOO_MANY_REQUESTS:
                return Fetched(
                    file_path=file_path,
                    url=url,
                    status_code=resp.status_code,
                    content_type=resp.headers.get("Content-Type", ""),
                    content=resp.content,
                )

        raise EcnThrottled(
            f"{file_path}: the portal returned 429 through all "
            f"{len(THROTTLE_BACKOFF_S)} backoffs. Stopping rather than recording "
            f"this file as missing — re-run later, and raise REQUEST_PAUSE_S."
        )

    def fetch_json(self, file_path: str, referer: str | None = None) -> Any:
        """GET one file and parse it, or fail loudly. Use when the file MUST be
        there; use `fetch` when its absence is itself the answer."""
        got = self.fetch(file_path, referer=referer)
        if not got.is_json:
            raise EcnError(
                f"{file_path}: expected JSON, got HTTP {got.status_code} "
                f"({got.content_type or 'no content-type'}) — the handler serves "
                f"its 403/404 page as HTML, so this is a missing file or a "
                f"changed access rule, not data"
            )
        return decode_json(got.content)

    def fetch_page(self, page_path: str) -> bytes:
        """GET an ordinary .aspx page (used by the spike to mine endpoints)."""
        resp = self._session.get(
            f"{self.base_url}/{page_path.lstrip('/')}", timeout=REQUEST_TIMEOUT_S
        )
        time.sleep(self.pause_s)
        return resp.content


def decode_json(payload: bytes) -> Any:
    """Decode a portal payload. Several files carry a UTF-8 BOM, which
    `json.loads` refuses; `utf-8-sig` strips it when present and is a no-op
    when it is not."""
    return json.loads(payload.decode("utf-8-sig"))
