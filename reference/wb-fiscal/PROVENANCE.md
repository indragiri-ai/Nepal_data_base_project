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

## RESOLVED FOR LOADING — the aggregate row disagrees with its own parts

**Status (2026-08-04): settled well enough to publish the aggregates, and only
the aggregates. The underlying question is still open with the World Bank.**

What settled it: the aggregate rows were checked against Nepal's own published
accounts (FCGO), and they match.

| Series | Dashboard | FCGO | Gap |
|---|---|---|---|
| FY 2018/19 revenue | 765,535.7 | 764,767.76 non-financing receipt | 0.10% |
| FY 2022/23 revenue | 913,786.1 | 910,370.97 non-financing receipt | 0.38% |
| FY 2018/19 expenditure | 957,980.1 | 944,351.58 recurrent + capital | 1.44% |

So the **aggregate is the trustworthy series** and it is loaded. The revenue
**category rows are still NOT loaded**: they do not sum to the aggregate in any
year after FY 2017/18, and the reason remains unestablished (a revenue-sharing
explanation fits FY 2018/19 to 0.12% but fails FY 2022/23 by 12%). Publishing
them would let a reader add four published numbers and get a fifth that
contradicts the published total. Question 3 of the founder's email to
Infonepal@WorldBank.org still asks what the aggregate represents; if it is
answered, the categories may become loadable.

The evidence that opened this issue is kept below, unchanged, because the
discrepancy itself is not explained — only worked around.

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

**Consequence.** Both readings cannot be published. Rule 1 says report, never
guess. The FCGO check above decided it: the aggregate matches Nepal's own
accounts and is published; the summed parts are not, and the categories are
withheld rather than relabelled into a total the source never states.

The harvester (`ingestion/worldbank/fiscal_harvest.py`) enforces this: its sum
check fails the run and writes no staging file, so the discrepancy cannot be
loaded by accident.

## Provincial figures — a different treatment, and why (2026-08-06)

The provincial sheets are handled the OPPOSITE way round from the federal ones,
and the reason is the source, not a change of mind.

- **Federal:** the source publishes an aggregate AND its parts, and they
  disagree. The aggregate is published (FCGO-verified); the parts are withheld.
- **Provincial:** the source publishes **no provincial aggregate at all** —
  only per-province, per-category rows. So each stored category value is the
  source's own figure, and the per-province TOTAL is derived by summing them.

Deriving a total is only allowed because it is gated against the source itself.
For every sheet, type, year and category, the seven provinces must sum to the
figure the same sheet publishes with no province filter:

    sum(seven provinces)  ==  the source's own all-provinces figure

That all-provinces figure comes from the source, so the check is not the
pipeline marking its own homework. It passes for **every category, year and
type** — e.g. FY2024 taxes, the seven provinces sum to 84,969.36, exactly the
published all-provinces value. A failure means a province or category went
missing, and the load stops rather than publishing a total that is quietly
short.

Loaded: Provincial Revenue, Provincial Expenditure and Provincial Grants, both
Budget and Actual, geographies NP01–NP07 — 1,078 observations under release 47.
Coverage is not the same for both types, because the source's is not: the
**Actual** series run FY 2018/19 – FY 2023/24 (six years) and the **Budget**
series FY 2019/20 – FY 2023/24 (five). The dashboard publishes no provincial
rows before those years, so the gap is the source's, not a harvesting loss —
the all-provinces cross-check would have caught a dropped year. Provincial
Financing and Provincial Fiscal Indicators are deliberately left for a later
pass.

### A correction to this file (2026-08-06)

An earlier draft of this section said the provincial data was **loaded on
2026-08-04**. It was not. The warehouse was checked on 2026-08-06 and held zero
provincial observations and no provincial indicators — the loader had been
written and tested, but no successful load had ever run. The load recorded
below is the first one. The earlier claim is corrected rather than quietly
deleted, because a provenance file that overstates what happened is the same
failure as data that overstates what a source says.

### The independent check WBF.S2 asks for — done (2026-08-06)

The sum check above is internal to the dashboard: it proves nothing was dropped
in harvesting, not that the World Bank's provincial figures match what the
provinces themselves published. WBF.S2 requires one provincial figure checked
against that province's own budget. **Two were checked, both for FY 2023/24
(BS 2080/81) budgeted expenditure, and both reconcile.**

**Bagmati (NP03)** — budget presented 16 June 2023:

| Line | Bagmati's own announced budget | This portal (WB dashboard) |
|---|---|---|
| Capital | 35,506.3 | 35,506.3 |
| Current / recurrent | 26,702.7 | 26,702.8 |
| Financial management | 500.0 | not in this sheet |
| **Total** | **62,709.0** | **62,209.1** |

**Koshi (NP01)** — budget presented 15 June 2023 by Chief Minister Hikmat
Kumar Karki (figures as the source reports them, in NPR billion):

| Line | Koshi's own announced budget | This portal (WB dashboard) |
|---|---|---|
| Capital | 18.23 | 18.23 |
| Current 14.39 + transfers to local levels 3.60 | 17.99 | 18.00 (recurrent) |
| Fiscal management | 0.01 | not in this sheet |
| **Total** | **36.24** | **36.23** |

Two things this establishes. First, the component figures match the provinces'
own numbers to the last decimal the sources publish — this is not a
coincidence at that precision. Second, **the residual is explained, not waved
away**: in both provinces the dashboard's total is short by exactly the
province's "financial management / fiscal arrangement" line (500.0 for Bagmati,
10.0 for Koshi), because that is financing, which the dashboard carries in a
separate Provincial Financing sheet that is not loaded. Add it back and the
totals agree exactly.

It also confirms a mapping that was otherwise a guess: the dashboard's
**"Recurrent expenditure" includes a province's fiscal transfers to local
levels**, not only its own current spending. Koshi's 17,999.3 is
14,396.3 current + 3,603.0 transfers.

Sources for the provincial side of this check:

- Koshi: <https://risingnepaldaily.com/news/28161> (The Rising Nepal,
  15 June 2023) — total Rs 36.24 bn with the four-way split.
- Bagmati: <https://english.ratopati.com/story/28314/budget-presented-by-bagmati->
  (Ratopati, 16 June 2023) — total Rs 62,709 m with capital, current and
  financial management stated separately.

**Honest limitation:** these are press reports of the budget speeches, not the
speech PDFs. The provinces' own documents were tried first and were not usable
here — Koshi's Budget Implementation Annual Report 2080/81 is a scanned image
with no text layer, and the fiscal tables in the Koshi Provincial Economic
Survey 2080/81 could not be located by text search because the PDF's Devanagari
font mapping is broken on extraction. Press reports of a budget speech quote
the tabled figures, and two independent provinces agreeing to the last
published decimal is strong; replacing them with the ministries' own PDFs (via
the GIWMS harvester that MOF.S1 / EDU.S1 will build) would make it airtight.

## Staying up to date (WBF.S4, 2026-08-06)

The dashboard publishes roughly annually and gives no notification. The step
file proposed watching the page's "Last Updated" string — but as recorded
above, **that string is not on the page**, and a watcher aimed at it would
never fire while looking like it worked.

So the watcher checks the **data**. `ingestion/worldbank/fiscal_watch.py`
re-harvests the nine federal aggregate series (the same `harvest()` the loader
uses, so there is no second parser to keep in step) and reduces them to a
fingerprint stored in `watch_fingerprint.json`: per series, how many years it
has, its newest year, and that year's value. Any new fiscal year, revised
headline figure, or renamed series moves the fingerprint.

`.github/workflows/wb-fiscal-watch.yml` runs it quarterly and opens a labelled
GitHub issue when it fires — a red run is easy to miss months later; an issue
is not. It touches no database and needs no secrets.

    make wb-fiscal-watch          # has it changed? exit 1 = yes
    make wb-fiscal-watch-update   # accept the current state as the baseline

Federal only, deliberately: a provincial harvest is ~45 minutes and the
provincial sheets ride the same publication cycle, so the federal series are
the canary at a cost of nine requests.

**The one blind spot, stated plainly:** a revision to an OLDER year that leaves
the newest year untouched does not move the fingerprint. Keeping every value
would make this file a second copy of the warehouse. Since both loaders are
idempotent, a re-run after any fire picks up older revisions anyway.

## Reproducing this

```
make wb-fiscal-acquire-dry    # list the sheets, fetch nothing
make wb-fiscal-acquire        # harvest all 16 into the raw lake + inventory
```

Raw payloads are archived to `worldbank/fiscal-dashboard/<timestamp>/sheets.json`
as one snapshot (each member keeps its own bytes, SHA-256 and source URL), so
every published figure traces back to the exact response that produced it.
