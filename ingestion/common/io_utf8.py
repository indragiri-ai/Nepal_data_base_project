"""Force UTF-8 on stdout/stderr (Phase 1 carry-forward Lesson 1).

The Windows console defaults to the legacy cp1252 code page. The moment a script
prints Devanagari (काठमाडौं) — or even an em-dash — cp1252 cannot encode it and
Python raises `UnicodeEncodeError`, killing the run. Phase 2 is Devanagari-heavy,
so EVERY entrypoint script must guarantee a UTF-8 console before it prints.

Usage — call once, first thing, at the top of every entrypoint:

    from ingestion.common.io_utf8 import configure_stdout_utf8

    configure_stdout_utf8()

It is safe to call more than once and safe on platforms that are already UTF-8
(macOS/Linux, or a Windows terminal with PYTHONUTF8=1): it simply does nothing.
"""

from __future__ import annotations

import sys


def configure_stdout_utf8() -> None:
    """Reconfigure stdout and stderr to UTF-8, tolerating any environment.

    Uses `TextIOWrapper.reconfigure` (Python 3.7+), which changes the encoding of
    the existing stream in place without replacing the file object — so it is
    harmless if the stream is already UTF-8, and a no-op if the stream does not
    support reconfiguration (e.g. it has been redirected to a plain buffer).
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="strict")
        except (ValueError, OSError):
            # Stream doesn't support reconfiguration (already-wrapped buffer,
            # closed stream, etc.). Nothing to do — leave it as-is.
            pass
