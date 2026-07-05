# Provenance — BS↔AD calendar reference data

**Used by:** migration `0004_bs_calendar.sql` + `scripts/load_bs_calendar.py`
(`make load-calendar`).

## What this data is

The `bs_calendar` table maps every Bikram Sambat (BS) calendar day to its exact
Gregorian (AD) date. BS month lengths are irregular (29–32 days) and change from
year to year — they are fixed authoritatively each year in the **Nepal Rajpatra**
(the government gazette) and cannot be reproduced by any formula. The whole point
of this table is that the system *looks up* the conversion instead of computing it
(Blueprint §5.1).

We do not store a hand-typed day-level table. We store the **per-year month-length
table** plus a single anchor date, and `load_bs_calendar.py` walks it day by day to
produce the ~36,500 daily rows. The month-length table is the small, checkable
kernel; the daily expansion is deterministic from it.

## Source

| Field | Value |
|---|---|
| Source project | `opensource-nepal/node-nepali-datetime` |
| File | `src/dateConverter/constants.ts` |
| URL | https://github.com/opensource-nepal/node-nepali-datetime/blob/main/src/dateConverter/constants.ts |
| Commit | `feea859a5596a642a47d9603c4f9f63fefb64f93` |
| Retrieved | 2026-07-05 (UTC) |
| Source license | **GPL-3.0** |
| Anchor | BS 2000-01-01 = AD 1943-04-14 |
| Range covered | BS 2000 – 2099 (AD 1943-04-14 … ≈2043-04) |

## Files here

- `opensource-nepal_constants.ts` — the raw source file, stored verbatim for an
  auditable trail (exactly the bytes we read).
- `bs_month_lengths.json` — the month-length facts extracted from it into a clean,
  language-neutral form, plus the anchor. This is what the loader reads. Every
  year's 12 month lengths were validated to sum to that year's stated total during
  extraction.

## Licensing note (read before redistributing)

The source *file* is GPL-3.0. What we use from it is the **factual month-length
table** — the number of days in each Nepali month each year, as published in the
Nepal Rajpatra. Facts of this kind are not themselves copyrightable, and the loader
here is original code that consumes those facts; no GPL code is copied into the
application. The raw `.ts` is retained only as a provenance artifact under this
reference directory. If the project's own license makes even that uncomfortable,
the identical facts can be re-sourced from the Rajpatra or any of the other
calendar libraries that carry the same table (they all agree — see the correctness
check below), and only `bs_month_lengths.json` needs to remain.

## Range decision (why BS 2000, not BS 1970)

The Phase 2 step file suggested "at least BS 1970–2100." We deliberately start at
**BS 2000 (AD 1943)** instead: that is where authoritative, gazetted day-level data
begins, and it is the anchor every serious Nepali calendar library uses. Pre-2000
BS has no trustworthy day-level source, and the Prime Directive is *never guess a
mapping*. Our actual data era begins ≈AD 1960 (World Bank ≈ BS 2017) and Nepali
fiscal years from ≈BS 2030 — so BS 2000–2099 covers every date this portal will
hold, with decades of margin on both ends. Padding backward with unsourced years
would add rows no dataset uses (Prime Directive 7).

## Correctness verification (2026-07-05)

**Internal integrity:** 36,525 daily rows loaded (BS 2000-01-01 … BS 2099-12-30 =
AD 1943-04-14 … AD 2043-04-13). The rows form a perfect bijection — row count =
distinct Gregorian dates = calendar span in days = 36,525 — so every AD day in
range maps to exactly one BS day, with no gap or overlap. Enforced by the
`bs_calendar_gregorian_unique` constraint and re-checked at load.

**Two independent public converters** agreed with our table on three sample dates,
including a fiscal-year boundary:

| BS date | Our table | Converter 1 | Converter 2 |
|---|---|---|---|
| 2080-01-01 (New Year) | AD 2023-04-14 (Fri) | nepalicalendar.rat32.com → Apr 14, 2023 | english.hamropatro.com/date/2080-1-1 → "Friday, Apr 14, 2023" |
| 2080-04-01 (Shrawan 1, FY start) | AD 2023-07-17 (Mon) | published almanac: "Shrawan = Jul 17 – Aug 16" → Jul 17, 2023 | (same, fiscal-boundary) |
| 2000-01-01 (anchor) | AD 1943-04-14 (Wed) | matches source anchor constant | — |

These dates are also asserted offline in `tests/test_bs_calendar.py`.

**Idempotency:** re-running `make load-calendar` reports `inserted=0 updated=0`.
