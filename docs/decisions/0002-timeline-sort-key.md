# Decision 0002 — One timeline: a date-based `sort_key` (YYYYMMDD)

**Date:** 2026-07-06
**Status:** Accepted (implemented in P2.S2)
**Relates to:** Blueprint §5.1 ("data attaches to a period, on one true timeline"); `time_periods` (migration 0002); P2.S2

## Context

`time_periods.sort_key` is an `integer` that orders periods along the timeline
(the API reads a series with `ORDER BY sort_key`). Phase 1 seeded calendar years
with `sort_key = year` — the bare integer `2023`, `2024`, ….

P2.S2 introduces Nepali fiscal years, which start mid-year (Shrawan 1 ≈ 17 July).
FY 2080/81 runs 2023-07-17 → 2024-07-15, so on a true timeline it belongs
**between** calendar 2023 and calendar 2024. With bare-year integer sort_keys
there is no integer between `2023` and `2024`: the two period types cannot
interleave. The step's own verification requires that a fiscal year "orders
correctly relative to the calendar years around it."

## Decision

Encode every period's `sort_key` as its **Gregorian start date, as an integer
`YYYYMMDD`** — `year*10000 + month*100 + day`:

- calendar 2023 → `20230101`
- FY 2080/81   → `20230717`
- calendar 2024 → `20240101`

`20230101 < 20230717 < 20240101`, so the fiscal year interleaves correctly. This
is one monotonic key for the whole timeline, works for any future period type
(quarters, months, census rounds), and fits `integer` (`20991231 < 2.1e9`).

## Why touching the existing calendar rows is safe

P2.S2 realigns the Phase-1 calendar-year rows onto this scheme. This changes only
the `sort_key` ordering field:

- No foreign key references `sort_key`; no `observations` row points at it.
- Each period's identity (`id`), dates, and labels are unchanged — observations
  still attach to the exact same period rows.
- The API's `ORDER BY sort_key` result is unchanged, because the new key is
  monotonic in year (calendar years still sort in the same order).

So the World Bank calendar periods are untouched in every meaningful sense; the
Phase-2 step's "keep the existing calendar-year periods untouched" is honored for
identity, dates, and labels, while ordering metadata is corrected to support two
calendars on one axis.

## Consequences

- `scripts/seed.py` (calendar years) and `scripts/seed_periods_ne.py` (fiscal
  years) share one helper, `ingestion.common.fiscal_periods.sort_key_for_date`,
  so the scheme has a single definition.
- The P2.S13 inflation milestone (NRB fiscal-year vs World Bank calendar-year on
  one axis) positions marks by each period's true `gregorian_start`/`end`; this
  sort_key is the coarse ordering that agrees with those exact dates.
