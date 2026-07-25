# Decision 0005 — Headline answers (one number per question)

**Date:** 2026-07-25
**Status:** accepted (founder policy; implements P2B.S4)
**Context:** With the full World Bank catalogue loaded (P2B.S3b) alongside the
National Census 2021 and NRB banking statistics, several real-world facts are now
measured by more than one source. Most visibly, "the population of Nepal" exists
as both a census enumeration (29.16M, 2021) and a World Bank modeled estimate
(~30M). Two different answers to the same question on one page erodes trust faster
than any missing feature.

## Decision

For any fact measured by multiple sources, the portal designates **one headline
answer**; the others are shown, **clearly labelled as an alternative estimate,
and never hidden or deleted**. This is a labelling and display-default policy, not
a data change — every value stays in the warehouse with full provenance.

**Which source is headline, by kind of fact:**

1. **Nepali-counted facts** — population, households, literacy, and other things
   Nepal itself enumerates (census, official registers): the **National
   Statistics Office (census)** is headline. World Bank figures for the same fact
   are labelled *"alternative estimate — World Bank"* (modeled/interpolated).
2. **Internationally-modeled or cross-country series** — GDP and its components,
   trade, inflation, and anything whose value is a comparison across countries:
   the **World Bank** is headline.
3. **Banking & monetary** — deposit/credit aggregates, interest rates, BFI
   ratios: **Nepal Rastra Bank** is headline.

## Mechanism

- `indicators.origin_source_id` (added in migration 0006) records where an
  indicator's data actually comes from — immutable provenance. The ingestion
  pipelines scope on this, so a demoted series keeps being refreshed.
- `indicators.preferred_source_id` records the **headline** source for the
  fact. For a standalone indicator it equals its origin; for a colliding one it
  points at the headline source. Seeded idempotently from
  `db/seeds/headline_sources.csv` (`make seed`).
- The API's `/v1/indicators` exposes each indicator's `source` (its origin) and
  `preferred_source` (the headline). When they differ, the indicator is an
  alternative estimate; the frontend badges it *"alternative estimate —
  {source}"* wherever it appears (sector pages, search — P2B.S5).

## Resolved collisions (census is headline; the WB twin is the alternative)

| Fact | Headline (National Statistics Office) | Alternative (World Bank) |
|------|----------------------------------------|--------------------------|
| Total population | `CENSUS_POP_TOTAL` | `POP_TOTAL` (SP.POP.TOTL) |
| Population growth rate | `CENSUS_POP_GROWTH` | `POP_GROWTH` (SP.POP.GROW) |
| Population density | `CENSUS_POP_DENSITY` | `EN_POP_DNST` (EN.POP.DNST) |
| Female population | `CENSUS_POP_TOTAL` (sex-disaggregated) | `SP_POP_TOTL_FE_IN` |
| Male population | `CENSUS_POP_TOTAL` (sex-disaggregated) | `SP_POP_TOTL_MA_IN` |
| Literacy rate | `CENSUS_LITERACY_RATE` (age 5+) | `ADULT_LITERACY` (SE.ADT.LITR.ZS, age 15+) |

**Note on literacy:** the census figure counts the literate population aged 5+,
while the World Bank series is *adult* (15+) literacy — a different age base. They
are related, not identical, so the WB value is a genuine alternative estimate, not
a redundant copy. Both are kept and labelled.

`CENSUS_SEX_RATIO` has no World Bank twin — it stands alone and is simply the
headline for that fact by default.

## Considered but NOT a collision (coexist as distinct indicators)

Per decision 0003 §3, two indicators collide only when they measure the **same
real-world concept**. The World Bank's monetary aggregates (broad money
`FM.LBL.BMNY.*`, domestic credit to private sector `FS/FD.AST.PRVT.GD.ZS`) are
**different constructs** from NRB's specific BFS ratios (credit-to-deposit,
deposits-to-GDP, weighted-average rates). They are not the same number measured
twice, so there is no headline conflict — they coexist as separate indicators,
each under its own source. No repointing.

## Unresolved (founder to decide next session — never picked silently)

| Fact | Options | Why deferred |
|------|---------|--------------|
| Domestic credit to private sector (% of GDP) | WB `FS.AST.PRVT.GD.ZS` vs WB `FD.AST.PRVT.GD.ZS` | An **intra-World-Bank** near-duplicate (two WB codes for nearly the same series), not a cross-source collision. Harmless for now; pick one as the display default when the finance sector page (P2B.S5) curates its charts. |

## Consequences

- Migration 0006 is additive (nullable → backfilled → NOT NULL); rollback drops
  the column. The WB ingestion now scopes on `origin_source_id`, which is stable
  under headline repointing (this replaces the temporary `preferred_source_id`
  scope noted in `ingestion/worldbank/pipeline.py`).
- No value is ever deleted or hidden; this decision only changes which number is
  shown first and how the others are labelled.
- New collisions are added by curating `db/seeds/headline_sources.csv` and
  extending the tables above — a human review step, never inferred by a pipeline.
