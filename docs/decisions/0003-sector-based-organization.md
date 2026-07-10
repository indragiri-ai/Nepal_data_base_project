# Decision 0003 — Sector-based organization, source-agnostic integration

**Date:** 2026-07-10
**Status:** accepted (founder decision)
**Context:** Two sources are live (World Bank API, NRB Banking & Financial
Statistics). Next up: National Census 2021, Ministry of Finance / Economic
Survey, labor statistics (ILOSTAT / Labor Force Survey), and import–export
data. The founder wants the portal organized **by sector, not by source** —
e.g. one "Macroeconomy" section fed by World Bank, NRB, and MoF together.

## Decision

1. **Sectors are a navigation label on indicators; sources are provenance on
   observations. They are independent axes.** The single `observations` fact
   table remains the only home for every number (Blueprint §2.1/§4.2); we
   never split storage by source OR by sector.

2. **Add a `sectors` reference table** (`code`, `name_en`, `name_ne`,
   `description`, `sort_order`) and an `indicators.sector_id` FK (nullable
   until backfilled, then NOT NULL). The existing broad `topic` column stays
   (stable, CHECK-constrained); `sector` is the finer, portal-facing grouping.
   Initial sector list (curated, extendable by seed, never invented by a
   pipeline):

   | code            | name                                   |
   |-----------------|----------------------------------------|
   | macro           | Macroeconomy                           |
   | banking         | Banking & finance                      |
   | fiscal          | Government finance                     |
   | external        | External sector (trade, remittances)   |
   | prices          | Prices & inflation                     |
   | labor           | Labor & employment                     |
   | demographics    | Population & demographics              |
   | social          | Health & education                     |
   | agriculture     | Agriculture                            |
   | energy_env      | Energy & environment                   |
   | governance      | Governance                             |

3. **Indicator naming rule (permanent):**
   - Same real-world concept measured by multiple sources → **one shared
     indicator code**, multiple datasets feeding it; `preferred_source_id`
     picks the display default; the UI cites every contributing source
     (Blueprint §4.3 — already implemented).
   - Publication-specific constructs (e.g. NRB C4 regulatory ratios) →
     source-prefixed codes (`NRB_BFS_*`), because no other source measures
     the same thing.
   - Deciding which case applies is a human review step during source
     onboarding, recorded in the seed CSV.

4. **Every new source follows the proven assembly line** (runbook
   `adding-a-data-source.md`; proven by the WB-API path and the NRB
   staging-and-review path):
   register (source/dataset/indicators+sector, curated) → acquire raw to the
   lake (hashed, immutable) → parse into staging (layout-specific, versioned)
   → human review (spot-check vs source) → quality gate → promote under a
   release → automatically exposed via API and sector pages.
   **The warehouse schema never changes for a new source.**

## Consequences / sequencing agreed

1. Sector table + backfill + sector navigation in the web app (small; first).
2. ILOSTAT labor statistics — clean API, reuses the WB adapter pattern;
   first real test of the shared-indicator rule (ILO vs WB unemployment).
3. Geography layer: provinces/districts/local units + 2015 crosswalk
   (Phase 2 steps P2.S4–S6) — prerequisite for census.
4. Census 2021 (sub-national; needs 3).
5. MoF / Economic Survey (fiscal years already seeded; PDF/Excel → the NRB
   staging pattern).
6. Trade: prefer primary sources (NRB BoP / customs) over aggregators (WTO —
   use only for gap-filling, cited as such). Commodity/partner splits go in
   `breakdowns` JSONB with documented keys.

Storage note: census-at-local-level and monthly trade by commodity will
eventually outgrow the Supabase free tier; revisit the plan (paid tier or
partitioning) when observations approach the free-tier limits — a capacity
decision, not an architecture change.
