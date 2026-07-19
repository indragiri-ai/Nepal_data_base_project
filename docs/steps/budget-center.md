# The Budget Center — three-tier budget tracking + dashboard — Step File

**Version 1.0 — 2026-07-19. Recon + product design by Fable 5; implementation
by any capable model. Founder's product vision (recorded): a dedicated,
visually striking Budget section tracking FEDERAL, PROVINCE, and LOCAL
(municipality) budgets — "the data everyone is looking for." House rules
apply.**

---

## Why this is the right bet (context for the implementer)

Budget data is Nepal's most-searched statistic every budget season (Jestha/
mid-June), and NO ONE offers all three government tiers in one accessible
place. The portal already owns every prerequisite: BS fiscal-year periods,
7 provinces + 77 districts seeded (P-codes), 753 municipalities extracted
(census recon), a choropleth engine, and census population (⇒ **per-capita
budget maps**, the killer view).

## Verified facts (2026-07-19)

- `mof.gov.np/category/redbook/` and related categories (same GIWMS CMS as
  `onboard-mof-publications.md` — the `var pdf` CDN extraction pattern
  applies) carry, among others:
  - **अन्तर सरकारी वित्तीय हस्तान्तरण** (Intergovernmental Fiscal Transfer):
    **content/1751 (FY 2083-84)** and **content/1526 (FY 2082/83)** — the
    annual budget annex listing federal transfers (equalization, conditional,
    complementary, special grants + revenue sharing) **per province AND per
    local government**. This is the LOCAL tier's data source — no need to
    visit 753 municipal sites.
  - **विनियोजन ऐन (Appropriation Act) २०८२/८३** (content/1531) and Economic
    Bills — the legal budget totals.
  - **Budget Speech English editions** (2025/26 content/1548, 2026/27
    content/1754) — headline numbers in English, annex tables.
  - The Red Book proper (व्यय अनुमानको विवरण — ministry/program-level detail)
    publishes per fiscal year; locate the actual Red Book volumes via the
    MOF.S1 index (the category feed mixes many item types — filter by title
    pattern, don't assume the category is clean).
- Provincial budgets: covered TWO ways — the WB fiscal dashboard
  (`onboard-wb-nepal-fiscal.md`, structured FY2018–24) and each province's
  own budget documents (later extension; 7 sites of varying quality — recon
  cost noted, not assumed).
- Grant-type procedures (special/complementary grants rules) also on the
  site — useful definitions for the glossary, not data.

## Dependencies / integration (do these in this order)

1. **MOF.S1** (publications mirror) — harvests all documents this needs.
2. **WBF.S1–S2** (WB fiscal) — provincial + federal aggregate series.
3. **NGP.S1–S2 or P2B.S8** — municipality geographies seeded (needed to
   attach per-LG transfers; until then BUD.S1 can still stage data keyed by
   the census NSO ids in `reference/census/`).
4. This file's steps then assemble the Budget Center.

---

### BUD.S1 — Intergovernmental transfers: per-province + per-municipality

**GOAL:** Every rupee the federal budget sends down — by grant type, by
recipient government, per fiscal year — in the warehouse.

**ACTIONS:** Instruct the implementing model:
> "From the raw mirror, take the IGFT documents for FY 2082/83 and 2083/84
> (content ids above; earlier years via the MOF.S1 index if present).
> Stability recon first: table structure per document (expect one table per
> grant type × recipient tier; likely hundreds of rows for 753 LGs).
> Extraction: these are large tabular PDFs — test pdfplumber AND camelot on
> real pages; if extraction is unreliable, check whether the document exists
> as Excel on the CDN (try the `var pdf` URL with .xlsx — sometimes both are
> uploaded) or STOP with a page-count + effort memo. Indicators:
> `BUDGET_TRANSFER_TOTAL` + one per grant type
> (`BUDGET_TRANSFER_EQUALIZATION`, `_CONDITIONAL`, `_COMPLEMENTARY`,
> `_SPECIAL`, `_REVENUE_SHARE` — match to the document's own categories,
> verified not assumed), unit NPR (magnitude read from the document —
> lakh/thousand rules with tests), geography = recipient (NP01–07 or the
> local unit), period = BS fiscal year, status final. LG name matching: join
> against the census municipality extraction (nso ids + district) — 753
> Devanagari names WILL have variants; unmatched names fail loudly into a
> curation report (never fuzzy-auto-match; the census alias precedent).
> Staged + reviewed (PDF-extracted). Cross-checks: column sums vs the
> document's own printed totals (exact); national total vs the budget
> speech's stated transfer figure."

**VERIFICATION:** per-table sums match printed totals; ≥95% of LGs matched
with the rest in the curation report; idempotent; gates green.

**COMMIT:** `BUD.S1: intergovernmental transfers by province + local government`

---

### BUD.S2 — Federal budget headline + composition

**GOAL:** Total budget, recurrent/capital/financing split, and (from the Red
Book) ministry-level allocations, per fiscal year.

**ACTIONS:** Instruct:
> "Sources in order of tractability: (1) Budget Speech ENGLISH annex tables
> (2025/26, 2026/27) — headline totals + composition; (2) Appropriation Act
> totals as the legal cross-check; (3) the Red Book for ministry-level
> detail — locate the volumes via the index; parse ONLY the summary
> (ministry × recurrent/capital) table, not the program-level thousands of
> pages (that's a later, separate decision). Indicators:
> `BUDGET_TOTAL`, `BUDGET_RECURRENT`, `BUDGET_CAPITAL`,
> `BUDGET_FINANCING`, and `BUDGET_BY_MINISTRY` with
> breakdowns={'ministry': <curated bilingual name>}. Cross-check federal
> totals against the WB fiscal dashboard series (differences reported with
> vintages, not forced). Staged + reviewed."

**VERIFICATION:** recurrent+capital+financing = total (document's own
identity); ministry sum ≈ total (reconciliation reported); 2 spot-checks vs
the English budget speech text.

**COMMIT:** `BUD.S2: federal budget totals, composition, ministry allocations`

---

### BUD.S3 — Province budgets

**GOAL:** Each province's own budget (not just transfers received).

**ACTIONS:** Instruct:
> "Primary channel: the WB fiscal dashboard provincial series (WBF.S2
> output) — already structured, FY2018–24. Extend with provincial budget
> speeches for the years after: RECON step first (7 provincial MoF/OCMCM
> sites; inventory what each publishes and in what format; effort memo per
> province; founder picks which to pursue). Do NOT promise all 7 —
> coverage-by-province is displayed honestly on the dashboard ('FY 2081/82:
> 5 of 7 provinces published')."

**COMMIT:** `BUD.S3: province budgets — WBF series + provincial-site recon memo`

---

### BUD.S4 — The Budget Center dashboard (`/budget`)

**GOAL:** The founder's vision: a dedicated, visually striking budget
section — dashboard style, three tiers, map-first.

**Design (locked; execute within the design system + dataviz method):**
1. **Hero band:** the current FY's federal budget as the hero number
   (Fraunces, huge), beside it composition as a **single horizontal stacked
   bar** (recurrent/capital/financing — 3 segments, validated palette, 2px
   gaps; NO pie), and delta vs previous FY. FY picker top-right (BS labels).
2. **"Where the money goes" band:** ministry allocations as a horizontal
   bar chart, top 10 + "Other", sorted descending, direct value labels.
3. **"Money to the provinces" band:** choropleth (7 provinces) of transfers
   — with a **per-capita toggle** (transfers ÷ census population — the
   feature nobody else has); beside it a compact 7-row table (absolute,
   per-capita, share).
4. **"Money to your municipality" band:** the differentiator. Search box
   ('Find your palika') over the 753 LGs → that LG's transfer breakdown by
   grant type, its district/province context, per-capita vs national
   median. Municipality choropleth when NGP.S2's map file lands; searchable
   table until then.
5. **Provinces' own budgets band** (BUD.S3 data): small-multiple bars, one
   per province, honest coverage notes.
6. Everywhere: CSV download, provenance ('Ministry of Finance, Government of
   Nepal — [document], FY …'), BS fiscal-year labels, bilingual ministry/LG
   names, and a short plain-language glossary (grant types) — definitions
   from the MoF's own procedure documents.
7. Navigation: 'Budget' becomes a first-class item in the header nav (and a
   sector-card on the landing page). It complements the Finance sector, not
   replaces it.
8. Performance: budget data is small; keep the route static + client-fetch;
   charts lazy; ≤120 kB first-load like every route.

**VERIFICATION:** hero numbers match warehouse values by hand-check; the
stacked bar sums visually and numerically; palika search finds 3 test LGs
(one per spelling-variant class); Playwright smoke extended; founder eyeball
on the dashboard before announcing.

**COMMIT:** `BUD.S4: the Budget Center — three-tier budget dashboard`

---

## Order & sessions

BUD.S1 (2–3 sessions; the PDF-table lift) → BUD.S2 (1–2) → BUD.S4 with
tiers 1+2+transfers live (2) → BUD.S3 recon (1) → BUD.S4 completes. Budget
season (Jestha/June) is the natural deadline each year: the annual refresh
is MOF.S1's scheduled harvest + re-running BUD.S1/S2 on the new documents
(idempotent). **Honesty note:** the local tier v1 = federal transfers TO
each municipality (what the documents publish), not each municipality's own
full budget — the dashboard labels this precisely; full LG budgets (SuTRA/
FCGO consolidated reports) are a possible future source, recorded as an
open question, not promised.
