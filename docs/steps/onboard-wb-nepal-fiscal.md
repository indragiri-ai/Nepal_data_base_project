# Onboarding: World Bank Nepal Fiscal Dashboard — Step File

**Version 1.0 — 2026-07-19. Recon by Fable 5; implementation by any capable
model. House rules apply (raw-first, staging for scraped data, idempotent,
report-never-guess, gates green, log every session).**

---

## What this source is (verified 2026-07-19)

- Public page: `worldbank.org/en/data/interactive/2026/02/10/nepal-fiscal-dashboard`
  — a shell embedding a **Tableau workbook** at
  **`https://dataviz.worldbank.org/views/NepalFiscalDashboard/Landingpage`**
  (embed API v3; server `dataviz.worldbank.org`).
- **Content (from the page's own text):** federal AND provincial fiscal data —
  budgets, revenue, expenditure — **FY2018 to FY2024**, compiled from "federal
  budget speeches (Ministry of Finance), provincial budget speeches
  (Provincial Ministry of Finance), consolidated financial statements
  (Financial Comptroller General Office), and Nepal Rastra Bank."
  Page states: *federal series complete; certain sub-national series have
  coverage caveats.* **Last updated: Feb 12, 2026.** Contact given:
  Infonepal@worldbank.org.
- **Why it matters to us:** public finance is an EMPTY sector on the portal,
  and per-province budget/spending is data almost nobody offers accessibly.
  Fits our machinery beautifully: BS fiscal-year periods (already built) ×
  7 provinces (already seeded, NP01–NP07) + federal (geography NP).
- **Access reality (probed):** the naive `…/Landingpage.csv` trick returns an
  HTML shell, not data — the workbook requires the **Tableau session
  protocol** (below). This is our most brittle acquisition to date; the step
  file therefore has explicit fallbacks and a STOP.
- **Provenance framing:** WB is the *compiler/distributor*; the underlying
  authorities are MoF / Provincial MoFs / FCGO / NRB. Record source = "World
  Bank — Nepal Fiscal Dashboard" with the underlying agencies named in the
  dataset notes and each indicator's definition (mirrors the ODN
  source-vs-distributor policy). License: worldbank.org content is generally
  CC BY 4.0 — **verify on the page/terms during S1 and record what you find;
  if unclear, note it and proceed (attribution given, public data), flagging
  in the license field as 'CC BY 4.0 (assumed, WB terms — verify)'. Do not
  skip recording this.**

---

### WBF.S1 — Channel spike: get ONE sheet's data out, whole and raw

**GOAL:** Prove the extraction channel and enumerate what the workbook
contains, before any modeling.

**ACTIONS:** Instruct the implementing model:
> "Attempt channels in this order, stopping at the first that yields data:
> **(A) Tableau session harvest** (the expected winner): (1) GET
> `https://dataviz.worldbank.org/views/NepalFiscalDashboard/Landingpage?:embed=y&:showVizHome=no`
> and capture the `X-Session-Id` response header; (2) POST
> `https://dataviz.worldbank.org/vizql/w/NepalFiscalDashboard/v/Landingpage/bootstrapSession/sessions/<session-id>`
> with form field `sheet_id=Landingpage` — the response is mixed
> length-prefixed JSON; parse the two JSON documents; (3) from the bootstrap
> payload enumerate the workbook's SHEETS/dashboards (look for
> `sheetPath`/`publishedsheets` structures) — this inventory is deliverable
> #1; (4) for each data sheet, pull data via the session endpoints — try, in
> order: `/vizql/w/…/v/<sheet>/viewData/sessions/<id>/views/<viewId>?…csv`,
> the `exportcrosstab` endpoints, and Tableau's
> `…/views/NepalFiscalDashboard/<SheetName>.csv?:embed=y` WITH the session
> cookie jar from step 1 (it often works once a session exists). Use a
> persistent cookie session throughout; realistic User-Agent; 1s delay
> between calls (be polite). **(B)** If A is blocked: check the workbook UI
> for enabled Download→Data/Crosstab permissions via the REST-ish
> `vizportal` endpoints, and search the WB Data Catalog
> (`datacatalog.worldbank.org`, API `datacatalogapi.worldbank.org`) for a
> published 'Nepal fiscal' dataset. **(C)** If both fail: STOP and report —
> the memo should recommend (c1) emailing Infonepal@worldbank.org for the
> underlying tables (the page invites contact) and/or (c2) falling back to
> the PRIMARY documents (FCGO consolidated financial statements at
> fcgo.gov.np — PDF/Excel, heavier but first-hand). Do not scrape rendered
> PNG/pixel data ever.
> Whatever channel works: store EVERY raw response in the raw lake under
> `worldbank/fiscal-dashboard/<sheet>/` before parsing anything, and commit a
> `reference/wb-fiscal/PROVENANCE.md` documenting the channel, session
> protocol details observed, sheet inventory, stated update date, and the
> license text found. Deliverables: sheet inventory + ONE full sheet's data
> as parsed rows + provenance file."

**VERIFICATION:** raw pages in the lake; sheet inventory committed; one
sheet's rows parsed and eyeballed (print 5 rows); provenance file written.

**IF IT GOES WRONG:** Tableau protocol versions vary — if `bootstrapSession`
404s, capture the exact JS-issued requests by reading
`tableau.embedding.3.latest.min.js`'s endpoint construction, or fetch the
embed page and mine `tsConfigContainer` JSON for the session route. Never
brute-force; three failed protocol variants = fall to (B)/(C).

**COMMIT:** `WBF.S1: fiscal dashboard channel spike — inventory + one sheet raw`

---

### WBF.S2 — Model and ingest the fiscal series

**GOAL:** Federal + provincial revenue/expenditure/budget series in the
warehouse on BS fiscal-year periods.

**Modeling decisions (made — implement, don't redesign):**
- Geography: federal series → `NP`; provincial series → `NP01`–`NP07` (map
  province names/numbers exactly as in the census work — number → P-code,
  fail loudly otherwise).
- Periods: **BS fiscal years** (FY2018–FY2024 in WB labeling = FY 2074/75 –
  2080/81 BS; VERIFY the dashboard's own FY labeling convention from the
  harvested labels before mapping — WB sometimes labels by ending Gregorian
  year. Whichever it is, map to our existing fiscal-year periods; if any FY
  period is missing, `make seed-periods-ne` covers it).
- Indicators: one per fiscal concept, NOT per sheet — expect the family:
  `FISCAL_REVENUE_TOTAL`, `FISCAL_REVENUE_TAX`, `FISCAL_EXPENDITURE_TOTAL`,
  `FISCAL_EXPENDITURE_CURRENT`, `FISCAL_EXPENDITURE_CAPITAL`,
  `FISCAL_BUDGET_TOTAL`, `FISCAL_TRANSFERS` (adjust to what the sheets
  actually contain — the registry mirrors reality, never forces it). Finer
  category detail (ministry/heading level) goes in
  `breakdowns={"category": …}` on the parent indicator. Budget-vs-actual: if
  both exist, they are SEPARATE indicators (`…_BUDGET` vs `…_ACTUAL`), never
  mixed in one series.
- Unit: NPR at the magnitude the dashboard uses — READ it from the harvested
  labels (likely NPR billions or millions); create `NPR_MILLIONS` or
  `NPR_BILLIONS` accordingly (never assume; a 1000× unit error is the classic
  fiscal-data failure).
- Status: `final` for actuals from FCGO statements; `provisional` if the
  dashboard marks recent-year figures preliminary (mirror their marking).
- **Scraped data ⇒ staging + review gate** (NRB pattern): extract → staging →
  spot-check → founder-visible approve → promote.

**ACTIONS:** harvest all data sheets (S1 machinery), parse with a
fail-loudly layout module (`ingestion/worldbank/fiscal_layout.py`, registry +
CSV locked by test — census pattern), stage, review, promote.
**Spot-checks (mandatory, independent channel):** verify federal total
expenditure and total revenue for ONE fiscal year against Nepal's published
budget documents (MoF Red Book / budget-speech figures — findable via MoF
publications) — exact or explained; verify one provincial figure against that
province's budget speech if locatable, else against the dashboard's own
rendered tooltip (weaker; say so in the log).

**VERIFICATION:** registry⇄CSV test; ≥2 spot-checks with sources cited;
idempotent re-run; quality-gate bands for fiscal magnitudes (positive, ≤ NPR
5,000 billion sanity ceiling — adjust to observed unit) demonstrated.

**COMMIT:** `WBF.S2: Nepal fiscal series FY2074/75–2080/81 — federal + provincial, staged+reviewed`

---

### WBF.S3 — Frontend: public finance on the Economy sector page

**GOAL:** The data visible and useful: a "Public finance" panel.

**ACTIONS:** On the Economy sector page (or, until the sector portal ships,
a new `/fiscal` route reachable from the landing sector cards): federal
revenue vs expenditure over the FYs (two-line chart, validated palette slots),
a province comparison view (7 provinces, one fiscal year — BAR form per the
dataviz skill's form rules, or the existing choropleth by province for a
single indicator via `/v1/data/geo` — both are legitimate; build the map
first since the machinery exists), budget-vs-actual where present, CSV
download, provenance block naming WB + MoF/FCGO/NRB and the FY window.
Fiscal years display with BS labels ("FY 2080/81") — the labels come from the
periods, already correct.

**VERIFICATION:** charts render with real data; sub-national coverage caveats
from the source page reproduced as a visible note; Playwright smoke extended
if it exists by then.

**COMMIT:** `WBF.S3: public finance dashboard — federal + provincial fiscal data live`

---

### WBF.S4 — Refresh strategy

The dashboard updates roughly annually (last: Feb 2026). NO cron — add a
**quarterly reminder row** to the ops docs (or a scheduled GitHub Action that
only CHECKS the page's "Last Updated" string and opens a notification if it
changed — 5 lines, no ingestion). Re-running the S1→S2 chain on an update is
idempotent by construction.

**COMMIT:** `WBF.S4: fiscal dashboard update watcher`

---

## Order & effort

S1 (spike, ~1 session — the risky one) → S2 (2 sessions) → S3 (1 session) →
S4 (minutes). If S1's channels all fail, total cost was one session and the
fallback memo tells the founder exactly what to do next (email WB / FCGO
primary documents). **Honesty note for the log:** this source is
WB-*compiled* government data behind a viz protocol — the most brittle
acquisition we've attempted; the raw-lake archive is what protects us (once
harvested, we never depend on the protocol again for history)."
