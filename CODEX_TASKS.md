# CODEX_TASKS — load the full NPHC 2021 census into the warehouse

**Goal:** ingest every useful variable from the 89 CSVs in `Census_data/` into the
`observations` warehouse — at national, province, district, and **municipality
(753 local unit)** level — following the project's rules exactly. Work top to
bottom through the tiers below. **One file (or one small group) per task.**

This file is written for the **OpenAI Codex CLI**. Read `CLAUDE.md` first — its
non-negotiable rules override everything. The golden reference implementation you
copy is **`ingestion/nso/census_local_units.py`** (it already loads population
from `Indv01`); every new loader mirrors its structure.

---

## Non-negotiables (from CLAUDE.md — do not relearn the hard way)

1. **Never guess.** Unknown category/label codes are **reported, not invented**.
   A parser that meets a label it can't resolve fails loudly.
2. **UTF-8 stdout.** Every entrypoint calls `configure_stdout_utf8()` first
   (Devanagari + em-dashes crash the Windows console otherwise).
3. **Raw first.** Archive the untouched source CSV to the raw lake
   (`lake.store(...)`) BEFORE parsing — see `census_local_units.py`.
4. **Reference data is seeded from CSVs in `db/seeds/`** (indicators, units),
   upserted idempotently. Never invent codes on the fly in a pipeline.
5. **Revisions never overwrite / everything idempotent.** Re-running a loader
   must load 0 the second time (the `is_latest` mechanics + change comparison in
   `census_local_units.py` handle this — copy that logic).
6. **Quality gate before any write.** Build `Candidate`s and call
   `run_quality_gate` (see `ingestion/common/quality.py`); a failure blocks the
   whole load.
7. **The three gates must be green before you commit:** `make lint`
   (ruff + mypy) · `make test` (pytest, offline) · `cd web && npm run build`.
8. **Supabase free tier:** batch inserts with `executemany` on short-lived
   connections (already done in the reference loader).

Do **not** commit `Census_data/` (it's gitignored — 220 MB). Do **not** touch the
frontend unless a task says so. Add a `make` target for each new loader.

---

## The geography model (how every row maps to our warehouse)

Every file has `prov, dist, gapa` numeric codes and `provname, dname, gapaname`
labels. Map each row to a geography by these rules (nothing else — no name
guessing):

| Row kind | Condition | Our geography code | Lookup source |
|---|---|---|---|
| National | `prov==0` | `NP` | constant |
| Province | `prov!=0, dist==0` | province P-code (`NP01`..`NP07`) | `reference/census/nso_geo_ids.csv` (`nso_province` → `our_code`) |
| District | `dist!=0, gapa==0` | district P-code (`NP0101`…) | `nso_geo_ids.csv` (`nso_district` → `our_code`) |
| **Municipality** | `gapa not in (0, 99)` | **official `adm3_pcode`** (`NP0101301`) | `reference/census/local_unit_crosswalk.csv` — key `(census_dist, census_gapa)` → `adm3_pcode` |
| Institutional | `gapa==99` | — | **skip** (barracks/prisons not tied to a unit; note the count) |

`local_unit_crosswalk.csv` and the 753 `local_unit` geographies are already
seeded. Province/district geographies exist too. A row whose `(dist, gapa)` is
**not** in the crosswalk → **fail with a report** (never guess the geography).

**Which levels to load per file:** load every level present in the file
(national/province/district/municipality). The `/population` drill-down UI already
reads whatever levels have rows — no frontend change needed to surface them.

---

## The two data shapes

Run `head -3` on a file to see which it is.

### Shape A — simple (one row per place; categories are columns)
Header: `prov,dist,gapa,provname,dname,gapaname,rowtotal,a_Foo,b_Bar,…`
Each non-geo/non-total column is a **category**. Model each as an observation
with a `breakdowns` key, e.g. `{"category": "a_TapPiped1"}`, OR as separate
indicators — pick per file and be consistent. `rowtotal` is the all-categories
total (load it as the headline, breakdowns `{}`). Tier 1 files are all Shape A.

### Shape B — cross-tab (extra dimension columns before `provname`)
Header e.g.: `prov,dist,gapa,sex,agegrp,provname,…,sexname,agegrpname,rowtotal,a_…`
The columns between `gapa` and `provname` are **dimensions** (`sex`, `agegrp`,
`occ1`, `litsts`, …), each with a `*name` label column. **`0` almost always means
"Total"** for a dimension (verify via the `*name` column — it says `"Total"`).
Model dimensions as `breakdowns` keys using the **label** (`sexname`,
`agegrpname`), and the value columns as either a further breakdown or separate
indicators. The **headline** value for a place = the row where every dimension is
`0`/Total and breakdowns is `{}`. These files are large (up to ~90k rows) — filter
to the rows/levels you need and batch inserts.

**Labels:** use the source's own `*name` columns for dimension labels. For the
`a_/b_/…` value-column codes, derive a human label **only if unambiguous from the
column name**; otherwise keep the raw code as the key and note it for human
review. **Never invent a meaning.** (The Tier-4 title-row files carry fuller
English category descriptions in their header rows — use those to label the
matching Shape-A file where one exists.)

---

## Indicator & unit conventions

- Indicator codes: `CENSUS_<THEME>` (e.g. `CENSUS_HH_DRINKING_WATER`,
  `CENSUS_POP_LITERACY`). Keep the existing `CENSUS_POP_TOTAL` etc. as-is.
- Seed new indicators in `db/seeds/indicators_census.csv` (curated, upserted);
  seed any new unit in `db/seeds/units.csv`. Units: population counts →
  `PERSONS`; household counts → add/​use `HOUSEHOLDS` (COUNT-like); shares → `PCT`.
- `topic`/sector: population/health/education/etc. per the existing census rows.
- Dataset is the existing "National Population and Housing Census 2021".
- name_ne for the categories: leave NULL unless a Nepali label is in the source;
  report the count (local-unit geography `name_ne` is separately still NULL —
  don't block on it).

---

## Per-file prompt (paste into Codex, fill in the FILE)

> Read `CLAUDE.md`, `CODEX_TASKS.md`, and `ingestion/nso/census_local_units.py`.
> Following that loader's exact pattern (raw-first archive, quality gate,
> idempotent change-only writes, geography mapping via the rules in
> CODEX_TASKS.md using `local_unit_crosswalk.csv` + `nso_geo_ids.csv`), write a
> loader for **`Census_data/<FILE>.csv`**, loading every geography level present.
> Decide the indicator(s), breakdowns, and units per CODEX_TASKS.md; seed new
> indicators/units in `db/seeds/`; add a `make` target `ingest-census-<slug>`.
> Verify a spot-check (e.g. a national/district total matches the file's own
> aggregate row) and idempotency (second run loads 0). Run `make lint` and
> `make test` and a `cd web && npm run build`. **Do not guess any label — report
> unknowns.** When green, commit with message `P2B.S7: <FILE> census loaded`.

---

## Loading order (work top to bottom)

**Tier 1 — simple, high value, easiest (Shape A, clean header).** Do these first.
- `Hhld05_FloorOfHouse` · `Hhld06_SourceOfDrinkingWater` · `Hhld07_TypeOfCookingFuel`
- `Hhld08_SourceOfLighting` · `Hhld09_TypeOfToiletUsed` · `Hhld10_HouseholdFacility`
- `Hhld11_FemaleOwnershipOfFixedAsset` · `Hhld12_SmallScaleBusiness`
- `Hhld13_HouseholdHavingDeath` · `Hhld17_AbsentHousehold`
- `Indv02_SizeOfPerson`
- (`Indv01_PopulationBySex` — **already loaded**; households column `nHhld` in it
  is still not loaded — add `CENSUS_HOUSEHOLDS` from it as an easy warm-up.)

**Tier 2 — one extra dimension (sex OR agegrp OR one category dim).**
- By sex: `Indv06_HouseholdHeadBySex` · `Indv07_PopulationByRelationship` · `Hhld18_AbsentPopnBySex`
- By age: `Indv03_PopulationBySingleYear` · `Indv04_PopulationByFiveYear` · `Indv20_PopulationBySchoolAttendance` · `Indv53_PopulationByEcoActivity` · `Hhld14_NumberOfDeathBySex` · `Hhld16_FemaleDeathByStatus`
- Fertility/one-dim: `Indv33_NumberOfChildrenEverBorn` · `Indv34_NumberOfChildrenDead` · `Indv35_NumberOfChildrenBorn` · `Indv40–48` (CEB/dead/born by occupation/industry/reason)

**Tier 3 — two-plus dimension cross-tabs (big; model breakdowns carefully).**
The headline (all-dims-Total) is the map-worthy value; the breakdowns power tables.
- Health/education/social: `Indv16_Disability` · `Indv17_LiteracyStatus` · `Indv18_EduLevel` · `Indv19_SchoolAttendance` · `Indv21_FieldOfEducatn` · `Indv10_MaritalStatus` · `Indv11_AgeAtFirstMarriage` · `Indv09_Nationality` · `Indv62_Sector` · `Indv66_Reason` · `Indv69/70_LivArrngOfChildren` · `Indv71_BirthRegistration`
- Migration: `Indv22–32` (place of birth / stay / migration by prov/belt/length/reason) · `Hhld19–23` (absentees abroad by country/reason/age/edu)
- Work: `Indv49–52` · `Indv54–61` · `Indv63–65` · `Indv68` · `Indv55_Occupation` · `Indv56_Industry` · `Indv57_OccupationAndIndustry` · `Indv60_EmploymentStatus`
- Deaths: `Hhld15_NumberOfDeathByCauseOfDeath`

**Tier 4 — title-row headers (custom header parsing; do last).**
`Hhld01_OwnershipOfHouse` · `Hhld02_FoundationOfHouse` · `Hhld03_OuterwallOfHouse`
· `Hhld04_RoofOfHouse` · `Indv05_SizeOfLocalities`. These have a multi-row title
header (skip the title/blank rows, read the real column names) and their headers
carry the best English category descriptions — use them to label matching Tier-1
files too.

---

## Coordination & hygiene

- **One agent on the repo at a time.** If Claude Code and Codex might overlap,
  work on a **branch** (`git switch -c census-load`) and open a PR, or take turns.
  Commit after each file so work is never lost.
- After each file: `make lint` · `make test` · `cd web && npm run build` green,
  then commit. Push in batches once the founder approves a deploy (loads are
  data-only — no visible change until the UI surfaces new indicators).
- End a working session by adding a `docs/PROJECT_LOG.md` entry (newest at top).
- If a file is genuinely ambiguous (labels you can't resolve, a geography that
  won't map), **stop and leave a note** in the commit / a `TODO` — do not force it.

When every tier is loaded, `/population` (and the sector pages) will expose the
full census — households, literacy, education, disability, migration, work — at
municipality level. That's the finish line.
