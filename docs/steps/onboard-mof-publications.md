# Onboarding: Ministry of Finance Publications (mof.gov.np) — Step File

**Version 1.0 — 2026-07-19. Recon by Fable 5; implementation by any capable
model. House rules apply. This is a PRIMARY source — the documents behind
every fiscal number — but it is PDF-heavy: the plan is deliberately
"library first, tables second".**

---

## Verified facts (2026-07-19)

- `mof.gov.np` runs the government GIWMS CMS (Prixa). Listing pages are
  `/category/<slug>/`; each publication is a `/content/<id>/<slug>/` page
  whose document URL is embedded in inline JS as **`var pdf = 'https://giwmscdnone.gov.np/media/pdf_upload/<name>.pdf'`**
  (CDN also appears as `giwmscdn.prixacdn.net`). Extraction = fetch content
  page → regex the `var pdf` value → download from the CDN.
- **The publication library (category slugs seen in the site nav):**
  `bulletin` (अर्थ बुलेटिन — the periodic economic bulletin, multiple issues
  a year incl. an annual statistical edition), `economic-survey` (आर्थिक
  सर्वेक्षण — the ANNUAL flagship with the statistical annex),
  `budget-speech` (बजेट वक्तव्य; English editions exist — "Budget Speech
  (English) 2026/27" was on the listing), `redbook` (व्यय अनुमानको विवरण —
  detailed expenditure estimates), `whitebook`, `yellowbook` (public
  enterprises review), `inter-government-financial-transfer` (province/local
  transfers), `half-yearly-elemental-assessment`, `report`, `press-release-
  budget`, `economic-act---bill`, and division-wise categories.
- Sample verified: the FY 2081/82 annual bulletin content page (id 1633)
  resolves to `…/media/pdf_upload/Annual%20Bulletin%202082%20Very%20Final_r6uzhvi.pdf`.
- Language: predominantly **Nepali** (Devanagari titles and content); some
  English editions (budget speeches). Everything is UTF-8; the cp1252
  console rule applies to every script.
- Authority: first-party (the Ministry itself). License: none stated —
  official public documents; attribute "Ministry of Finance, Government of
  Nepal"; record "no license text published".
- Relationship to the WB fiscal dashboard source
  (`onboard-wb-nepal-fiscal.md`): MoF is the PRIMARY for the same fiscal
  aggregates (WB compiles from these very documents). The WB channel gives
  structured FY2018–24; MoF gives **timeliness** (bulletins continue
  monthly/periodically), **detail** (Red Book line items), and the
  **independent spot-check channel** the WB script already requires.

## Translation policy (binding — answers "can we translate?")

1. **Table labels/headers → YES, via a curated bilingual mapping**, exactly
   like our reference-data rule: a human-reviewed CSV
   (`reference/mof/label_map.csv`: nepali_label, english_label, notes) maps
   each Nepali row/column label to our English indicator names. Machine
   translation may DRAFT the CSV; a human (founder or reviewer) approves
   every row before it is used; unmatched labels fail the parse loudly.
   Nepali originals are always preserved (name_ne fields, raw lake).
2. **Publication titles → YES**, same curated-CSV approach, for the library
   index (bilingual titles, both displayed).
3. **Prose/body translation → NO.** We are a data portal, not a document
   translation service; we link to the original PDF and present extracted
   NUMBERS with bilingual labels. (A summary/translation feature would be a
   separate product decision — not smuggled in here.)

---

### MOF.S1 — The publications library: harvest EVERYTHING raw (no parsing)

**GOAL:** A complete, growing mirror of MoF publications in the raw lake +
a machine-readable index — the archive is valuable even before any table is
parsed, and it makes every later step offline-repeatable.

**ACTIONS:** Instruct the implementing model:
> "Write `ingestion/mof/acquire.py`: crawl the category listing pages
> (start set: bulletin, economic-survey, budget-speech, redbook, whitebook,
> yellowbook, inter-government-financial-transfer,
> half-yearly-elemental-assessment; listings may paginate — follow), collect
> content pages, extract each page's `var pdf` URL, and download NEW
> documents into the raw lake under `mof/<category>/<content-id>/` (sha256,
> source URL, retrieval date — the standard sidecar). Idempotency ledger:
> `reference/mof/manifest.json` keyed by content id + file hash (NRB
> bfs_acquire is the model). Politeness: sequential, 1–2s delay, realistic
> UA. Build `reference/mof/publications_index.csv`: content_id, category,
> title_ne (as published), title_en (BLANK — curated later per the
> translation policy), bs_date_guess (parse from the title where present —
> e.g. 'मंसिर अंक ५ (२०८२)' — unparseable stays blank, never guessed),
> pdf_url, sha256, retrieved_at. `make mof-acquire`. Report: documents per
> category, total size (watch the 1 GB Supabase storage budget — if the full
> mirror exceeds ~400 MB, STOP and propose category priorities to the
> founder)."

**VERIFICATION:** manifest idempotent (re-run downloads 0); index CSV row
count = content pages found; 3 random PDFs open correctly (non-zero pages);
storage usage reported.

**COMMIT:** `MOF.S1: publications library — full raw mirror + index`

---

### MOF.S2 — Artha Bulletin: parse the stable statistical tables (monthly-ish)

**GOAL:** The bulletin's recurring fiscal/macro summary tables in the
warehouse — the timely primary series that outruns the WB dashboard's FY2024
cutoff.

**ACTIONS:** Instruct:
> "Stability recon FIRST (the NRB C4 method): open the last 6–8 bulletin
> PDFs from the raw mirror; identify which statistical tables recur with a
> stable structure (expect: revenue summary, expenditure summary, debt,
> possibly forex/macro snapshot — verify from the documents, don't assume);
> produce a stability report naming the 1–3 tables to parse and their page/
> layout signatures. THEN: parser (pdfplumber or camelot — pick by testing
> on the real PDFs; whichever extracts the chosen tables losslessly) with a
> per-table registry (Nepali labels → indicators via the curated
> `label_map.csv`; unknown label = failed run). Numerals: confirm whether
> figures use Arabic or Devanagari numerals (convert Devanagari digits
> deterministically if present). Units: read from the table headings (लाख/
> करोड/अर्ब — lakh/crore/arba conversions are exact powers of ten; encode
> the conversion table with tests, never eyeball). Periods: bulletin issues
> map to BS months/FYs (existing machinery). PDF-extracted ⇒ **staging +
> review gate**, spot-checks: 2 values per issue against the PDF read by
> eye, plus one cross-check against the WB fiscal dashboard series where
> periods overlap (differences reported with both values — they are
> different vintages of the same government data; do not force agreement).
> `make mof-bulletin-extract` / promote flow."

**VERIFICATION:** stability report committed; label_map.csv human-approved
(the founder or reviewer initials the commit message); spot-checks exact;
lakh/crore conversion tested; idempotent.

**COMMIT:** `MOF.S2: Artha Bulletin tables — staged, reviewed, cross-checked`

---

### MOF.S3 — Economic Survey statistical annex (annual; check for Excel FIRST)

**GOAL:** Nepal's richest annual macro table set, IF a structured format
exists.

**ACTIONS:** Instruct:
> "For the latest two Economic Surveys (2082/83, 2081/82): inspect their
> content pages AND the listing for companion items — MoF has historically
> published the statistical annex ('statistical tables') as separate
> Excel/zip downloads in some years. If an Excel annex exists: onboard it
> via the standard staged Excel flow (this supersedes PDF parsing — far
> cheaper and lossless). If PDF-only: STOP and report table inventory +
> effort estimate; the founder decides whether annex parsing (large) is
> worth it versus the WB/NRB structured channels that cover much of the
> same ground."

**COMMIT:** `MOF.S3: Economic Survey annex — [excel onboarded | decision memo]`

---

### MOF.S4 — Publications library on the portal (founder-visible, cheap)

**GOAL:** The mirrored library becomes a public feature: a searchable,
bilingual "Government publications" page — value delivered without parsing a
single table.

**ACTIONS:** Instruct:
> "API: `GET /v1/publications?category=` serving the index (title_ne,
> title_en where curated, category, date, link to the ORIGINAL MoF/CDN URL —
> we link out, we don't rehost publicly). Frontend: a `/publications` page in
> the design system: category filter chips, search box, bilingual titles,
> 'Source: Ministry of Finance' attribution. Curate title_en for at least
> the bulletin + economic-survey + budget-speech categories via the
> translation policy CSV before shipping. Add to the Economy sector page as
> a 'Primary documents' link block."

**VERIFICATION:** page renders the real index; search works; every link
resolves (spot-check 5); Playwright smoke extended if present.

**COMMIT:** `MOF.S4: government publications library (bilingual index)`

---

## Order & effort

MOF.S1 (1 session — pure harvest, low risk) → MOF.S4 (1 session — visible
win, no parsing) → MOF.S2 (2–3 sessions — the PDF work) → MOF.S3 (spike).
Refresh: add `mof-acquire` to the monthly scheduled workflow (P2B.S2) — new
bulletins land in the library automatically; parsing new issues stays
human-gated. **Honesty note:** PDF table extraction is the most
labor-intensive channel in our stack — that's why the library-and-index
steps come first and stand on their own even if S2/S3 wait.
