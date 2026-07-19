# Onboarding: CEHRD Education Statistics (Flash Reports + IEMIS) — Step File

**Version 1.0 — 2026-07-19. Recon by Fable 5; implementation by any capable
model. House rules apply. This fills the EDUCATION sector with Nepal's
official school statistics — the right-way answer to the edusanjal.com
question (a private directory we declined on copyright + no-statistics
grounds; recorded in the log).**

---

## Verified facts (2026-07-19)

- **`cehrd.gov.np`** (Center for Education and Human Resource Development,
  MoEST) runs the **same GIWMS/Prixa CMS as mof.gov.np** — listing pages
  `/category/<slug>/`, content pages `/content/<id>/<slug>/`, and the
  document URL embedded as **`var pdf = 'https://giwmscdnone.gov.np/media/pdf_upload/…'`**.
  Verified live: **Flash 1 Report, 2081 (2024)** → content/14179 →
  `…/Flash%201%20Report%202081%20(2024)_hzq1zgz.pdf`.
  ⇒ **The MoF acquire machinery works here unchanged** — generalize it, don't
  duplicate it (see EDU.S1).
- Relevant sections seen in the nav: `/category/flash-report/`,
  `/category/status-report/`, `/category/research-report/`, `/publications`,
  `/downloads`, `/statistics`, `/reports`, plus many notices. The
  flash-report category page shows only recent items — **older Flash Reports
  (the series runs back ~two decades, two per year historically: Flash I ≈
  school year start, Flash II ≈ year end) must be hunted across
  /publications, /downloads, and content search**, not assumed absent.
- **IEMIS** (Integrated Educational Management Information System) at
  **`emis.cehrd.gov.np`** — HTTP 200, live. This is the school-level MIS
  behind the Flash Reports; whether it exposes public dashboards/APIs or
  logins-only is EDU.S2's spike.
- The founder's original link `cehrdservices.moest.gov.np` was **unreachable
  from outside (connection failed instantly)** — likely an internal service
  or intermittently up; re-probe once during EDU.S2 and record the outcome;
  do not block on it.
- Authority: first-party government (MoEST/CEHRD). License: none stated —
  official public statistics; attribute "CEHRD, Ministry of Education,
  Science & Technology"; record "no license text published".

## What a Flash Report contains (why this is the education mother lode)

Annual official statistics for ALL of Nepal's ~35,000 schools: number of
schools by level/type, student enrollment by grade/level/sex, teachers by
qualification/sex, and the headline access indicators (Gross/Net Enrollment
Rates, survival/completion), disaggregated **by district and province** — 
which joins our seeded P-codes directly and feeds district choropleths.

---

### EDU.S1 — Publications harvest (generalize the GIWMS harvester)

**GOAL:** Every CEHRD statistical publication mirrored raw + indexed —
Flash Reports as far back as the site holds them.

**ACTIONS:** Instruct the implementing model:
> "REFACTOR FIRST: lift `ingestion/mof/acquire.py`'s core (category crawl →
> content pages → `var pdf` extraction → raw lake + manifest) into a shared
> `ingestion/common/giwms.py` parameterized by base URL + category slugs;
> MoF and CEHRD acquires become thin configs (test locks both). CEHRD start
> set: flash-report, status-report, research-report, publication + the
> /publications, /downloads, /statistics, /reports pages (these may be
> different templates — inspect and adapt; unknown page shapes are reported,
> not skipped silently). Hunt older Flash Reports explicitly (search the
> index for 'Flash' across ALL harvested categories; report the year
> coverage found, e.g. 'Flash I 2070–2081'). Raw lake path
> `cehrd/<category>/<content-id>/`; manifest + index CSV per the MoF
> pattern (title_ne, title_en blank-until-curated, year guess from title).
> Politeness rules apply. Report documents-per-category + total size vs the
> storage budget."

**VERIFICATION:** shared GIWMS module tested; both MoF and CEHRD configs
green; Flash year-coverage reported; idempotent re-run downloads 0.

**COMMIT:** `EDU.S1: CEHRD publications mirrored (shared GIWMS harvester)`

---

### EDU.S2 — IEMIS spike: is there structured data behind the portal?

**GOAL:** Know whether school-level structured data is publicly reachable —
it would beat PDF-parsing entirely.

**ACTIONS:** Instruct:
> "Recon `emis.cehrd.gov.np` (and re-probe `cehrdservices.moest.gov.np`
> once): what loads without login? Look for public dashboards, school-search
> pages, report generators, or JSON/XHR endpoints behind them (the census
> and ECN techniques: read the bundles, watch the XHRs, replay with plain
> requests). If a public school-list or statistics endpoint exists: sample
> it, archive raw, report shape + coverage — that becomes the preferred
> channel for school counts and possibly enrollment. If login-only: STOP
> for this channel, record it, and EDU.S3 (Flash PDFs) carries the load.
> NEVER probe past a login wall or guess credentials."

**COMMIT:** `EDU.S2: IEMIS channel spike — [endpoints found | login-only recorded]`

---

### EDU.S3 — Flash Report core tables → the warehouse

**GOAL:** The headline education series, by district and province, across as
many years as the mirror holds.

**Modeling decisions (made):**
- Indicators (registry + CSV locked by test, census pattern):
  `EDU_SCHOOLS_TOTAL` (COUNT, breakdowns {"level"}), `EDU_STUDENTS`
  (PERSONS, breakdowns {"level","sex"}), `EDU_TEACHERS` (PERSONS,
  breakdowns {"level","sex"}), `EDU_GER` and `EDU_NER` (PCT, breakdowns
  {"level","sex"}), `EDU_STR` (student-teacher ratio, RATIO, breakdowns
  {"level"}). Match to the tables the reports ACTUALLY contain — adjust
  names to reality, never force.
- Geography: district rows → P-codes (name matching with the census alias
  precedent — Devanagari and English both appear across years; unmatched
  fails loudly). Province + national rows too.
- Periods: the school year (Baisakh-start academic year) → map to the BS
  fiscal-year periods ONLY IF the report defines the school year identically
  — VERIFY from the report's own definition section first; if the academic
  year differs, add a `period_type='academic_year'` via migration (CHECK
  extension) rather than mislabeling. Report the decision.
- PDF-extracted ⇒ staging + review; lakh/thousand conversions under test.

**ACTIONS:** stability recon across the mirrored years FIRST (which tables
recur, how layouts drift era to era — parse only proven-stable ranges, defer
the rest with a note), then parser + staging + review + promote, year by
year, newest first. **Spot-checks per year:** 2 values against the printed
PDF; national totals cross-checked against the ODN Ministry-of-Education
datasets where they overlap (independent channel, already licensed cc-by).

**VERIFICATION:** registry⇄CSV test; district match ≥95% with curation
report; spot-checks exact; idempotent; school-year mapping decision recorded.

**COMMIT (per year-batch):** `EDU.S3x: Flash Report <years> — staged, reviewed, loaded`

---

### EDU.S4 — Education sector goes deep on the frontend

**GOAL:** The Education sector page becomes a real dashboard.

**ACTIONS:** On the Education sector page: enrollment trend (national,
by level, sex toggle), **district choropleth** of NER/GER via the existing
`/v1/data/geo` machinery, teacher/student ratios, and the census literacy
map cross-linked (two sources, one sector — decision-0005 labeling applies:
census literacy vs Flash enrollment are DIFFERENT concepts, label precisely,
never merge). CSV everywhere; provenance "CEHRD Flash Report <year>".

**VERIFICATION:** map renders district education data; labels distinguish
census vs CEHRD series; Playwright smoke extended.

**COMMIT:** `EDU.S4: education dashboard — enrollment, NER/GER maps, ratios`

---

## Order & effort

EDU.S1 (1 session) → EDU.S2 (1, cheap spike) → EDU.S3 (3–5 sessions, the PDF
lift, newest years first) → EDU.S4 (1–2). Refresh: CEHRD acquire joins the
monthly scheduled harvest (P2B.S2); new Flash Reports land automatically,
parsing stays human-gated. **Future companion source (not this file):**
University Grants Commission annual reports for higher education — a
paste-the-link recon away.
