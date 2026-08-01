# Provenance — World Bank Nepal Fiscal Dashboard

**Written during WBF.S1, 2026-08-01. Everything below was observed directly;
nothing is inferred from documentation. Where a fact could not be verified it
says so.**

## The source

- **Public page:** <https://www.worldbank.org/en/data/interactive/2026/02/10/nepal-fiscal-dashboard>
- **Workbook:** `https://dataviz.worldbank.org/views/NepalFiscalDashboard/Landingpage`
  (Tableau Server, build `v_202422507101539`)
- **Workbook owner (from its own config):** Prabin Dongol
- **Coverage:** FY2018–FY2024, three tiers of government — federal, provincial
  **and local**. (The 2026-07-19 recon recorded federal + provincial only; the
  workbook also carries five Local Level sheets.)
- **Contact published on the page:** Infonepal@WorldBank.org

**Who actually produced the numbers.** The World Bank is the *compiler and
distributor*, not the origin. The page states the indicators are derived from
"verified government records from the federal budget speeches (Ministry of
Finance), provincial budget speeches (Provincial Ministry of Finance),
consolidated financial statements (Financial Comptroller General Office), and
Nepal Rastra Bank, covering fiscal year (FY) 2018 to FY2024." Source must be
recorded as "World Bank — Nepal Fiscal Dashboard" with MoF / Provincial MoFs /
FCGO / NRB named in the dataset notes and indicator definitions.

## Licence — NOT VERIFIED, recorded as such

The dashboard page carries **no explicit licence statement**. A text scan of
the page found no "Creative Commons", no "CC BY", and no "licence"/"license"
sentence anywhere. World Bank content is generally CC BY 4.0, but that was not
confirmed *for this page*.

Per the step file, the licence is therefore recorded as
**`CC BY 4.0 (assumed, WB terms — verify)`** and must be carried in that exact
form until someone confirms it — ideally by asking Infonepal@WorldBank.org.
Attribution is given regardless.

The page also carries no crawlable "last updated" string; the recon's
"Last updated: Feb 12, 2026" could not be re-confirmed from the page text.

## The channel (what actually works)

The recon expected the full Tableau session protocol — `X-Session-Id`,
`bootstrapSession`, length-prefixed JSON — and warned this would be our most
brittle acquisition. **It is not needed.** What works:

```
1. GET  /views/NepalFiscalDashboard/<View>?:embed=y   -> sets session cookies
2. GET  /views/NepalFiscalDashboard/<View>.csv        -> real text/csv
```

Both on one `requests.Session`. No browser, no session id, no JSON parsing.

The recon's note that `<view>.csv` "returns an HTML shell, not data" is correct
**only for a cold request**. The shell is what you get without the cookie from
step 1. That single missing ingredient was the whole difficulty.

Things that were tried and are NOT required: `bootstrapSession/sessions/<id>`,
mining `tsConfigContainer` for a session route, `vudcsv`, `exportcrosstab`.

**Fragility.** The dependency is now just "a session cookie, then `.csv`",
which is far less likely to break than the vizql protocol. If the CDN starts
serving shells to non-browser clients, `fetch_sheet` raises rather than parsing
the shell. Once harvested, the raw-lake archive means history never depends on
this channel again.

## What the publisher permits

Read from the live workbook config (`tsConfigContainer`) on 2026-08-01:

| flag | value | meaning |
|------|-------|---------|
| `allow_export_data` | `true` | data export is permitted |
| `allow_summary` | `true` | the aggregated summary behind a view is permitted |
| `allow_view_underlying` | **`false`** | row-level underlying data is withheld |
| `allow_filter`, `allow_select` | `true` | the view may be driven |
| `allow_save`, `allow_authoring` | `false` | no write access (nor wanted) |

We take **summary CSV only**. `allow_view_underlying: false` is the publisher's
explicit choice and the acquirer must not be extended to work around it.

## Sheet inventory (from the workbook's own `visible_sheets`)

18 sheets; 16 carry data. Machine-readable copy in `sheet_inventory.json`.

| Tier | Sheets |
|------|--------|
| Federal | Revenue · Expenditure · Financing · **Debt Stock** · Fiscal Indicators |
| Provincial | Revenue · Expenditure · Financing · Fiscal Indicators · **Grants** · **GDP** |
| Local Level | Revenue · Expenditure · Financing · Fiscal Indicators · **Grants** |
| Not data | `Landing page` (chrome) · `lisa_dashboard` (internal scratch) |

Debt stock, grants (intergovernmental fiscal transfers) and provincial GDP are
beyond what the recon anticipated.

## Shape of the data

Columns are Tableau field names, e.g. for Federal Revenue:
`Year1, fed_measure_%tot, Group0..Group4, Type1, Year1`.

- **`Group0`–`Group4`** are the fiscal classification hierarchy, coarse to fine.
  `*` marks a level not drilled into in the current view state.
- **`Type1`** is `Actual` or `Budget` — these are **separate series** and must
  become separate indicators, never mixed.
- **Unit: `NPR Million`.** This is **stated by the data itself** — the
  provincial and local sheets carry a `Local Unit` column whose value is the
  literal string `NPR Million`. It was read, not assumed. (A 1000× unit error
  is the classic fiscal-data failure; this removes the guess.)

### View state IS the data — the one real constraint

A sheet's CSV contains exactly what its current view renders:

- **Federal** sheets default to all seven fiscal years at the top of the
  hierarchy — 7 rows.
- **Provincial / Local** sheets default to a **single year (FY2024) aggregated
  over all places** — 1–5 rows.

So a plain harvest is one slice, not the full grid. Tableau URL filter
parameters drive the view, **verified working** on 2026-08-01:

| filter | effect (Provincial/Federal Revenue) |
|--------|-------------------------------------|
| `Fiscal year=FY2020` | returns FY2020 instead of FY2024 |
| `Province Name=Bagmati` | Bagmati only — 20,704.84 vs 84,969.36 for all |
| `Fiscal year` + `Province Name` | compose correctly |
| `Group2=Taxes` | drills the hierarchy — 640,169.3 of 766,036.1 |
| `Type1=Budget` | budget 802,223.22 vs actual 766,036.1 (FY2018) |

**Filter values must match the source's own spelling exactly.**
`Province Name=Bagmati` returns data; `Bagmati Province` returns **zero rows**
with no error. An unmatched filter value therefore looks identical to "no data"
and must be treated as a loud failure in S2, never as an empty result.

## First figures seen (FY2018, federal, NPR million, Actual)

Preliminary only — recorded to show the channel returns real numbers. **These
are not yet spot-checked**; WBF.S2 must verify against MoF Red Book /
budget-speech figures before anything is published.

| Series | FY2018 |
|--------|--------|
| Revenue and grants | 766,036.1 |
| of which Taxes | 640,169.3 |
| Expenditure | 967,633.1 |
| Financing | −116,586.07 |
| Debt stock | 917,052.9 |

Magnitudes are consistent with Nepal's published federal accounts (order of
NPR 0.7–1.0 trillion), which supports the `NPR Million` reading — but
consistency is not verification.

## OPEN ISSUE — the aggregate row disagrees with its own parts (2026-08-01)

**Status: BLOCKING. No fiscal data has been loaded into the warehouse.**

On Federal Revenue (`Type1=Actual`), the aggregate row — the one with
`Group2 = *`, which should be "revenue and grants, all categories" — equals the
sum of its four categories in FY2018 **exactly**, and in no other year.

| dashboard year | aggregate row (`Group2=*`) | Taxes + Grants + Other revenue + Miscellaneous receipt | difference |
|---|---|---|---|
| FY2018 | 766,036.1 | 766,036.1 | **0.0** |
| FY2019 | 765,535.7 | 862,564.7 | +97,029.0 |
| FY2020 | 764,732.9 | 864,919.6 | +100,186.7 |
| FY2021 | 901,099.25 | 1,012,040.75 | +110,941.5 |
| FY2022 | 1,013,490.1 | 1,141,336.3 | +127,846.2 |
| FY2023 | 913,786.1 | 1,034,033.5 | +120,247.4 |
| FY2024 | 979,141.2 | 1,106,008.1 | +126,866.9 |

Two things point at the **aggregate row** as the odd one out rather than the
categories:

1. It is nearly flat across FY2018–FY2020 — 766.0, 765.5, 764.7 (NPR bn) —
   which is not a plausible path for Nepal's federal revenue over three years.
   The sum of parts over the same years (766.0, 862.6, 864.9) moves as revenue
   actually did.
2. The four categories are individually plausible in level and trend.

**What was ruled out.** Simple nesting does not explain it: no subset of the
four categories (dropping Miscellaneous receipt as a child of Other revenue,
or excluding Grants) reproduces the aggregate for FY2020 or FY2024.

**What this is NOT.** It is not a parsing bug — the figures above are the
source's own strings, and FY2018 reconciles perfectly through the same code
path. It is not the fiscal-year mapping either; that would shift years, not
change one series' level while leaving the other coherent.

**Consequence.** Both readings cannot be published. Loading the aggregate would
understate federal revenue by 12–13% in six of seven years; loading the summed
parts would publish a total the source does not itself state. Rule 1 says
report, never guess, so **nothing is loaded** until this is resolved.

**How to resolve, in order of preference:**
1. Ask the World Bank (Infonepal@WorldBank.org) what the aggregate row
   represents — this is question 3 in the drafted email.
2. Spot-check both readings for one year against the MoF Red Book / budget
   speech. Whichever matches the published national figure is the true total,
   and the other must be excluded or relabelled.
3. Only then load, with the resolution recorded in each indicator's
   `definition_en` so the reasoning stays auditable.

The harvester (`ingestion/worldbank/fiscal_harvest.py`) enforces this: its sum
check fails the run and writes no staging file, so the discrepancy cannot be
loaded by accident.

## Reproducing this

```
make wb-fiscal-acquire-dry    # list the sheets, fetch nothing
make wb-fiscal-acquire        # harvest all 16 into the raw lake + inventory
```

Raw payloads are archived to `worldbank/fiscal-dashboard/<timestamp>/sheets.json`
as one snapshot (each member keeps its own bytes, SHA-256 and source URL), so
every published figure traces back to the exact response that produced it.
