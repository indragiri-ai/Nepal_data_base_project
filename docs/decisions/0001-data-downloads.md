# Decision 0001 — Data downloads: CSV + Excel, Nepal-scoped, with provenance

**Date:** 2026-06-13
**Status:** Accepted (to be implemented in Phase 3; foundation in Phase 1 API)
**Relates to:** Blueprint §1 (vision), §3.6 (frontend downloads), Roadmap Phase 3; Master Prompt §3.5 (`/v1/data.csv`)

## Context

The World Bank (and similar portals) let you download a variable as a single
bulk file containing **every country**, leaving the user to find and clean
Nepal's rows themselves. The founder identified this as a key pain point: our
portal should hand users a **clean, Nepal-only extract of exactly what they
asked for**, ready to use.

This is not a nice-to-have — it is the portal's core differentiator. Blueprint
§1: *"Not a file dump. Every dataset is harmonized into one common structure."*

## Decision

1. **Downloads are first-class.** Users can download any indicator/selection as a
   file scoped to the geographies and periods they chose — never an all-countries
   dump.
2. **Two formats: CSV and Excel (`.xlsx`).** CSV for tooling/programmatic use;
   Excel because it is what most Nepali researchers, journalists, and officials
   actually open.
3. **Excel files are self-documenting** — two sheets:
   - **Data**: tidy table (indicator, geography, period, value, unit).
   - **About this data**: provenance — source, dataset, release date, license,
     indicator definitions, footnotes.
   So every downloaded file carries its own citation (Blueprint §1: *"every number
   carries its source"*), which a raw all-countries dump does not.
4. **Built on the API, not a separate path.** Downloads serve the same
   Nepal-filtered, provenance-carrying data the API already returns
   (Master Prompt §3.5) — no second source of truth.

## Where it lands in the build

- **Phase 1 (P1.S10):** the API already returns Nepal-only, filtered data with a
  provenance block — the foundation. No UI download button yet.
- **Phase 3 (public portal):** the polished CSV/Excel download buttons and the
  two-sheet Excel writer (standard Python library, small effort).

## Consequences

- A small dependency (an `.xlsx` writer such as `openpyxl`) is added in Phase 3.
- The API's provenance block must carry everything the "About this data" sheet
  needs (license, definitions, footnotes) — already required by Master Prompt §3.5,
  so no new burden.
- Revisit if/when sub-national (province/district) data exists: "Nepal-scoped"
  then means user-selected geographies, which the design already supports.
