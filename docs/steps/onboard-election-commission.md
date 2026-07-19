# Onboarding: Election Commission of Nepal — Step File

**Version 1.0 — 2026-07-19. Recon by Fable 5; implementation by any capable
model. House rules apply (raw-first, idempotent, report-never-guess, gates
green, log every session). This source fills the GOVERNANCE sector — currently
empty.**

---

## Verified facts (2026-07-19)

- `election.gov.np/en` is a React SPA whose backend API base is
  **`https://election.gov.np/admin/public/api/`** (found in
  `main.*.chunk.js`) — serves site content (notices, press). Low data value;
  the statistics live elsewhere:
- **`result.election.gov.np`** (HTTP 200) — an **ASP.NET results portal**
  (jQuery/JQGrid era) whose landing links include
  **`PRVoteChartResult2082.aspx`** and **`MapElectionResult2082.aspx`** —
  i.e. it currently serves the **2082 BS House of Representatives election
  results** (proportional-representation vote charts, result maps), with
  UI in Nepali (UTF-8 — force UTF-8 stdout in every script; the recon
  itself hit the cp1252 console crash). Earlier cycles (2079 BS / 2022,
  2074 BS / 2017) are expected behind the same portal or its archive pages —
  enumerating them is ECN.S1's job.
- **`voterlist.election.gov.np`** (HTTP 200) — the voter roll. **PRIVACY
  BOUNDARY, binding: we NEVER ingest individual-level voter data** (names,
  IDs, addresses). Only aggregate counts OFFICIALLY PUBLISHED by the ECN
  (registered voters per district/constituency, by sex where published).
- Authority: the ECN is the constitutional election authority — first-party
  source. License: none stated; official public records, attribute clearly
  ("Election Commission of Nepal"), record "no license text published".

## Sensitivity policy (binding — election data is politically charged)

1. **Final published results only.** Never scrape live counting during a
   future election; ingest only results the ECN has finalized/published.
2. **Neutral presentation.** Party results ordered by votes or alphabetically
   — no editorial framing; colors NEVER borrow party brand colors (use the
   portal's validated categorical palette; parties beyond slot capacity fold
   to "Other" per the dataviz series-cap rule).
3. Aggregates only (see privacy boundary above).
4. Every chart cites "Election Commission of Nepal" + the election's full
   name and date.

## What this source yields (target indicators)

| Indicator family | Geography | Breakdowns | Period |
|---|---|---|---|
| `ELECTION_VOTERS_REGISTERED` | district (77) & national | `{"sex"}` if published | election year |
| `ELECTION_TURNOUT_PCT` | district & national | — | election year |
| `ELECTION_VOTES_PR` (PR party votes) | national (& province if published) | `{"party"}` | election year |
| `ELECTION_SEATS` (seats won) | national | `{"party", "system": "fptp"/"pr"}` | election year |

Periods: the existing calendar-year periods (election year), with the exact
election date + BS year in each indicator's definition (e.g. "House of
Representatives election, 2082 BS / 2026-03-…, ECN final results"). One
`releases` row per election cycle ingested.

---

### ECN.S1 — Channel spike: map the results portal's data endpoints

**GOAL:** A verified inventory of which elections are served and the exact
endpoints that return structured data — before any modeling.

**ACTIONS:** Instruct the implementing model:
> "On `result.election.gov.np`: fetch the landing page and the two known
> pages (`PRVoteChartResult2082.aspx`, `MapElectionResult2082.aspx`). ASPX +
> JQGrid apps load data via XHR — read the pages' inline JS for the grid
> `url:` configs and chart data endpoints (they typically return JSON or
> XML). Enumerate: which election cycles are available (2082? 2079? 2074?
> local elections?), at which granularity (national / province / district /
> constituency), and which endpoints serve (a) PR party vote totals, (b)
> FPTP constituency winners/seats, (c) registered-voter and turnout counts.
> Probe politely (sequential, delays). Store every probed response raw under
> `ecn/results/<cycle>/…` in the raw lake. If the portal resists static
> analysis (endpoints built dynamically), use one Playwright session to
> observe the XHR calls, then REPLAY them with plain requests — the pipeline
> itself must never depend on a browser. Deliverables:
> `reference/ecn/PROVENANCE.md` (endpoints, cycles, granularity, samples,
> the privacy + sensitivity policies restated) + one cycle's PR vote table
> parsed and printed (top 5 parties, UTF-8 stdout — party names are
> Devanagari)."
> STOP if all data turns out to be image/PDF-only — report with the ECN's
> published results books (PDF) as the fallback channel and an effort
> estimate for staged PDF extraction.

**VERIFICATION:** endpoint inventory committed; ≥1 cycle's party votes parsed
with plausible totals (sum of party votes ≤ registered voters); raw archived.

**COMMIT:** `ECN.S1: results portal endpoints mapped + first cycle sampled`

---

### ECN.S2 — Voter registration & turnout by district

**GOAL:** Registered voters and turnout, per district and national, for every
available cycle.

**ACTIONS:** Instruct:
> "From the S1 endpoints (or the ECN's published district-wise voter
> statistics if the portal lacks them — the main site's API/notices and
> `voterlist.election.gov.np`'s AGGREGATE pages may carry district tables):
> ingest ELECTION_VOTERS_REGISTERED and ELECTION_TURNOUT_PCT per district.
> District names → P-codes via the established mapping (census alias
> precedent; number→code only, fail loudly on unmatched). Scraped/structured
> data from a first-party portal: direct load is acceptable IF the endpoint
> is machine-served JSON; anything hand-extracted from HTML tables goes
> through staging+review. Quality gate: registered voters per district in
> (1,000, 2,000,000); turnout in (10, 100]%. Spot-check the national
> registered-voter total against the figure in ECN's own press release for
> that election (independent channel)."

**VERIFICATION:** 77/77 districts resolved; national total matches the press
figure; idempotent; gates green.

**COMMIT:** `ECN.S2: voter registration + turnout by district, per cycle`

---

### ECN.S3 — Party results (PR votes + seats)

**GOAL:** The headline democratic data: party vote shares and seats per
election.

**ACTIONS:** Instruct:
> "Ingest PR party vote totals (`ELECTION_VOTES_PR`, breakdowns
> {'party': <name as published, both scripts if available>}) and final seat
> counts (`ELECTION_SEATS`, breakdowns {'party', 'system'}) for each cycle
> S1 found. Party names: store EXACTLY as the ECN publishes (Devanagari
> primary; English transliteration in a reference CSV
> `reference/ecn/party_names.csv` curated during review — never
> auto-transliterate). Small parties: store ALL (storage is trivial);
> display-time folding handles the long tail. Cross-check: PR seat
> allocation derived from vote shares should reconcile with published seat
> totals — differences reported (threshold rules), not silently accepted.
> Staging+review gate for any hand-parsed table."

**VERIFICATION:** per cycle: party vote sum sanity vs turnout; seat totals =
house size (275 federal); spot-check 2 parties' figures against ECN press/
result books.

**COMMIT:** `ECN.S3: party votes + seats per election cycle`

---

### ECN.S4 — Governance sector goes live

**GOAL:** The empty Governance page becomes real.

**ACTIONS:** On the Governance sector page (or `/governance` route if the
sector portal isn't built yet): turnout choropleth by district (existing
`/v1/data/geo` + ChoroplethMap machinery — this is the eye-catcher), a party
vote-share chart per cycle (horizontal BAR, votes descending, top 8 +
"Other" — per the dataviz form + series-cap rules, portal palette, NO party
brand colors), registered-voters trend across cycles, CSV downloads, ECN
attribution + the neutrality note. Election picker if multiple cycles loaded.

**VERIFICATION:** map + bars render from warehouse data; Playwright smoke
extended if present; neutrality policy visibly followed.

**COMMIT:** `ECN.S4: governance dashboard — turnout map + party results`

---

## Order & effort

ECN.S1 (spike, 1 session — the risky one) → S2 → S3 (1–2 sessions each) →
S4 (1 session). Refresh: none needed between elections; after a future
election, re-run S1→S3 for the new cycle ONLY once ECN publishes final
results (policy #1). If S1 hits the PDF-only wall, the fallback memo decides
before any further spend.
