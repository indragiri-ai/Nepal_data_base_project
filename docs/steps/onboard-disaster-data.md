# Onboarding: Nepal's disaster record, 1971 → today — Step File

**Version 1.0 · written 2026-09-07 · follows the house step format and the
standing rules in `docs/nepal-data-portal-master-prompt.md` §6.**

Standing rules apply to every step here: raw before parsed · idempotent
re-runs · report-never-guess · staging + review for human-made files · UTF-8
stdout · provenance on every chart · plain language to the founder ·
PROJECT_LOG entry every session. All three gates green before any commit:
`make lint` · `make test` · `cd web && npm run build`.

---

## Why this source, and why it is not just a tenth sector

The founder's challenge, 2026-09-07: *if we are not adding anything new to how
the portal presents data, rethink it* — and the intention is not this year's
floods but **the entire disaster record of Nepal**.

An audit of `web/components/` on that date found the portal has exactly three
visual forms — line chart, bar chart, shaded-region map — and **nothing live
anywhere**. Disaster data is the only data the portal has taken on that is at
once event-level, precisely located, daily-updating and about human harm. It is
therefore the only one that earns new presentation rather than more cards:

| New form | Component | Why nothing else needed it |
|---|---|---|
| Point map | `IncidentMap.tsx` | No other source has per-record coordinates |
| Time scrubbing | `TimeRangeControl.tsx` | No other source is 55 years of dated events |
| Live gauge vs threshold | `RiverStatusPanel.tsx` | Nothing else on the portal is live |
| Event feed | `IncidentFeed.tsx` | No other source has individual records to list |

---

## What these sources ARE

**BIPAD** (`bipadportal.gov.np`) is run by **NDRRMA**, the National Disaster
Risk Reduction and Management Authority. It is an **origin, not an aggregator**:
the incidents are the government's own records, fed by police and local-
government reporting. So `sources` names NDRRMA and `datasets` names the BIPAD
portal — the same distinction ODN.S2 drew between the Kalimati Market Board and
Open Data Nepal.

**DesInventar** is the UNDRR loss-database methodology; Nepal's instance was
built by **NSET** with UNDP and MoHA. Its records are the pre-BIPAD era. It is
also an origin for our purposes — nobody else republishes these 24,257 rows.

**USGS** is the United States Geological Survey's global earthquake catalogue.
An international origin, deeper in time than any Nepali seismic record online.

---

## Verified facts bank (2026-09-07 unless noted — cite, do not re-derive)

### BIPAD — `https://bipadportal.gov.np/api/v1/`, open, no key

- Collections: `incident`, `loss`, `hazard`, `province`, `district`,
  `municipality`, `ward`, `river`, `rain`, `earthquake`, `alert`, `document`,
  `resource`, `organization`, `project`, `citizen-report`.
- **Total incidents: 63,151** (binary search on `offset`). Earliest
  **2011-04-14**; the 2015 Gorkha earthquake is present (2015-04-25).
- `?incident_on__gt=` / `?incident_on__lt=` / `?ordering=incident_on` all work,
  so refreshes are incremental.
- `?expand=loss` inlines the whole loss record — no second request per incident.
- **THE PAGING TRAP:** every list response reports
  `"count": 9223372036854775807`. The portal does not count its rows. Page until
  a page comes back empty; never show that number to a reader.
- `incident` fields: `id`, `title`, `titleNe`, `point` (GeoJSON, lon/lat),
  `wards` (ward ids), `incidentOn`, `reportedOn`, `hazard` (id), `loss`,
  `streetAddress`, `verified`, `approved`, `source`, `dataSource`.
- `loss` fields: `peopleDeathCount` / `peopleMissingCount` /
  `peopleInjuredCount` — each also split **Male / Female / Other / Unknown /
  Disabled** — plus `peopleAffectedCount`, `familyAffectedCount`,
  `familyRelocatedCount`, `familyEvacuatedCount`, `livestockDestroyedCount`,
  `infrastructureDestroyed*` / `infrastructureAffected*` for House, Road,
  Bridge, Electricity, `infrastructureEconomicLoss`, `agricultureEconomicLoss`,
  `estimatedLoss`.
- `hazard`: `id`, `titleEn`, `titleNe`, `color`, `type` ∈ {natural,
  non natural}. Known ids include 10 Fire, 11 Flood, 16 High Altitude,
  17 Landslide.
- `river`: `title`, `basin`, `point`, `waterLevel`, **`warningLevel`**,
  **`dangerLevel`**, `waterLevelOn`, `status`, `steady`, station/ward ids.
- `rain`: `averages[]` for 1/3/6/12/24-hour intervals, each with `value` and
  `status.{warning,danger}`.
- `earthquake`: `magnitude`, `point`, `address`, `eventOn` (source: NSC).
- `alert`: `title`, `titleNe`, `point`, `affectedDemography.{maleCount,
  femaleCount, householdCount}`, `startedOn`, `expireOn`, `referenceType`
  (e.g. `fire`, from ICIMOD satellite detection).
- Geography lists: `province` 7, `district` 77, `municipality` **774**,
  `ward`. Each has `title_en`, `title_ne`, `code` (BIPAD's own slug),
  `centroid`, `bbox`, and its parent's id.

### DesInventar Nepal

- `https://www.desinventar.net/DesInventar/download/DI_export_npl.zip`
  (13.5 MB; note **`npl`**, not `np` — the `np` URL 404s).
- Contains `DI_export_npl.xml` (182 MB) plus `regions`/`district`/`village`
  shapefiles.
- **24,257 records, 1971 → 2013, 32,758 deaths.** By decade: 1970s 1,758 ·
  1980s 2,125 · 1990s 4,577 · 2000s 9,994 · 2010s 5,803.
- Hazards: fire 6,004 · flood 3,953 · epidemic 3,516 · landslide 3,208 ·
  accident 1,708 · thunderstorm 1,453 · hail storm 763 · cold wave 647 ·
  strong wind 508 · plague 326 · rains 256 · earthquake 227 · forest fire 224 ·
  snow storm 194.
- Record fields: `level0`/`name0` (development region), `level1`/`name1`
  (district), `level2`/`name2` (VDC), `evento` (hazard), `lugar`, `fechano` /
  `fechames` / `fechadia` (Y/M/D), `muertos` (deaths), `heridos` (injured),
  `desaparece` (missing), `afectados` (affected), `vivdest` / `vivafec` (houses
  destroyed / damaged), `damnificados`, `evacuados`, `reubicados`, `cabezas`
  (livestock), `nhectareas`, `kmvias`, `nescuelas`, `nhospitales`, `valorloc` /
  `valorus` (loss, local / USD), `causa`, `glide`, `uu_id`.
- **Every record has `latitude` 0 and `longitude` 0** — checked across all
  24,257. This data maps at district level and must never be drawn as points.
- Its `level0`/`level1` values ARE the pre-2015 structure: 5 development
  regions, 75 districts (16 / 19 / 16 / 15 / 9 per region). This is where
  `db/seeds/geographies_old.csv` came from.

### USGS

- `https://earthquake.usgs.gov/fdsnws/event/1/query` (and `/count`), free,
  no key. Nepal box `26.3–30.5 N, 80.0–88.3 E`: **1,360 events M4.0+ since
  1900**, 607 at M4.5+ since 1970.

### Deferred, with the reason

- **EM-DAT** (1900 →): open access for **non-commercial use only**. Link to it;
  do not republish its rows.
- **ReliefWeb** (UN OCHA): API v1 is decommissioned; v2 returns 403 without a
  registered `appname`. Register first, then revisit.
- **ICIMOD** glacial lakes / GLOF: reports located, machine-readable download
  unconfirmed.

---

## Modelling decisions (made — do not revisit)

1. **Incidents get their own table**, `disaster_incidents`, not `observations`.
   An incident has an identity, a point and several facts attached to that one
   identity; `observations` stores one number per indicator × geography ×
   period × breakdowns, and two floods in one district on one day would collide
   into a single cell. Yearly totals derived from the incidents DO go into
   `observations`, so the data still reaches search, sector cards, choropleths
   and CSV export.
2. **Incident rows may be UPDATED.** Rule 5 (revisions never overwrite) governs
   published statistics. A BIPAD incident is a live operational record — a
   death toll rises as reports arrive — and the portal must show the current
   count. `first_seen_release_id` / `last_seen_release_id` record when a row was
   first taken and last confirmed; every run's untouched payload stays in the
   raw lake.
3. **No PostGIS.** Coordinates are two doubles with a Nepal bounding-box CHECK.
   The only geometric question — which district contains this point — is
   answered before insert by ray casting against the boundary files the website
   itself draws (`ingestion/common/geo_point.py`).
4. **Places are resolved by evidence, never by fuzzy name matching.** See the
   next section.
5. **Pre-2015 data stays on pre-2015 boundaries** (blueprint §5.2), with
   `geography_crosswalk` for comparison across the break.
6. **NULL ≠ 0 in impact columns.** NULL means the source published no figure;
   0 means it published a zero. The difference matters when totals are summed.

---

## The geography problem, and how it was solved

Neither source speaks P-codes.

- BIPAD uses its own slugs and ward ids. Of its 830 places, only 669 carry a
  name our gazetteer also uses within the same district — "Phaktanglung" for
  our "Phaktanlung", "Solududhkunda" for "Solu Dudhkunda", and 159 more.
- DesInventar uses the pre-2015 75 districts and their VDCs.

**Each place is resolved twice, independently**: an exact name match within its
district (case and punctuation stripped, nothing else), and its own centroid
tested against the official boundary. `evidence` on every crosswalk row records
which supported it. Results on 2026-09-07: **669 agreed, 0 disagreed**, 159
were resolved by location alone. Two independent methods never contradicting
each other is what justifies trusting the boundary method.

Three ways it refuses to guess:

- **Contested places.** BIPAD's published centroid for *Yemunamai* falls inside
  neighbouring *Durga Bhagawati*'s polygon, so both claimed one municipality and
  the real Yamunamai was left unclaimed. When two places claim one geography,
  **neither is trusted** — both go to review, and the answer comes back through
  `db/seeds/bipad_geography_overrides.csv` with the reasoning written down.
- **Not-a-municipality.** BIPAD lists 774 municipalities where Nepal has 753.
  The 21 extras are national parks, wildlife reserves, hunting reserves and the
  Lumbini development area. They are listed in
  `reference/bipad/crosswalk_unresolved.csv` with that reason; incidents inside
  them are placed by the incident's own coordinates.
- **Split districts.** Nawalparasi and Rukum were divided in 2015 and nobody has
  published how to apportion their earlier records, so they have **no crosswalk
  row at all**. Their pre-2015 data stays at the old district and is reported
  as such.

---

## The steps

### DIS.S1 — Foundations ✅ DONE 2026-09-07

**GOAL:** the tables, the reference data and the place-resolution machinery,
with nothing loaded and nothing visible yet.

**DELIVERED:**
- `db/migrations/0009_disaster_foundations.sql` (+ rollback):
  `geography_crosswalk`, `bipad_geography_crosswalk`, `disaster_hazards`,
  `disaster_incidents`.
- `ingestion/common/geo_point.py` — `BoundaryIndex.for_level(...).locate(lon, lat)`,
  ray casting, no geometry dependency, reading `web/public/maps/*.json` so a
  located point lands in the polygon a reader sees.
- `ingestion/bipad/client.py` — paged, retry-once, UTF-8-safe reader that stops
  on an empty page rather than trusting `count`.
- `ingestion/bipad/draft_crosswalk.py` — builds the crosswalk from evidence,
  rejects contested places, applies reviewed overrides.
- Seeds: `geographies_old.csv` (5 regions + 75 districts),
  `geography_crosswalk.csv` (73 one-to-one), `bipad_geography_crosswalk.csv`
  (830), `bipad_geography_overrides.csv` (2 reviewed).
- `scripts/seed.py` seeds all four.

**VERIFIED:** migration applies **and rolls back** cleanly against the live
database; 918 geographies (838 current + 80 old); 830 BIPAD places covering
**all 77 districts and all 753 local units**; 0 contradictions; database
247 MB of 500 MB after seeding; BIPAD's true incident count **63,151**;
`make lint` clean, `make test` 374 passed, `npm run build` green.

### DIS.S2 — Incident ingestion + the point map (first visible feature)

**GOAL:** every BIPAD incident in the warehouse, and a map of them on the site.

> **ACTIONS for the implementing model.**
> Build `ingestion/bipad/pipeline.py` on the Kalimati template
> (`ingestion/opendatanepal/kalimati_pipeline.py`): register NDRRMA in
> `sources` and BIPAD in `datasets`; load `disaster_hazards` from `/hazard/`
> first, failing loudly on an unknown hazard; page `/incident/?expand=loss`
> **archiving each page to the raw lake before parsing any of it**; resolve each
> incident's geography from **its own coordinates** via `BoundaryIndex`, falling
> back to the ward→municipality crosswalk only when a point is absent, and
> **rejecting** (counting in `ingestion_log.rows_rejected`) anything that
> resolves to neither; upsert on `(dataset_id, source_incident_id)` setting
> `last_seen_release_id`; support `--since` for incremental runs and `--dry-run`.
> Then the API: `GET /v1/incidents` (bbox, date window, hazard, geography
> filters), `GET /v1/incidents/{id}`, `GET /v1/hazards`, with a new
> `MAX_INCIDENT_ROWS = 2000` in `api/policy.py` enforced through the existing
> `bounded()`. Then the frontend: `IncidentMap.tsx` — a **third** ECharts
> wrapper registering `ScatterChart` + `GeoComponent` (leave `EChart.tsx`
> line/bar-only and `ChoroplethMap.tsx` region-fill-only, per the existing
> one-wrapper-per-form convention) — plus `IncidentFeed.tsx`,
> `TimeRangeControl.tsx`, a `disasters` entry in `web/lib/sectors.ts` and its
> icon in `SectorCards.tsx`.

**VERIFICATION:** three named incidents match BIPAD's own site field for field ·
a re-run inserts 0 new rows · rejected count is 0, or every rejection is
explained · a `/v1/incidents` request with no filters is refused by
`MAX_INCIDENT_ROWS` · the map draws points at real places · gates green.

### DIS.S3 — The 55-year archive + the aggregate side

**GOAL:** 1971 onward in the warehouse, and disaster figures behaving like every
other indicator.

> **ACTIONS.** `ingestion/desinventar/pipeline.py`: download the zip to the raw
> lake, **stream**-parse the 182 MB XML (never load it whole), map `level1` →
> `geographies_old` via `DESINVENTAR_LEVEL1=`, load 1971–2010 with NULL
> coordinates. The 2011–2013 overlap with BIPAD is **not merged**: BIPAD owns
> 2011 onward, DesInventar 2010 and earlier, and the cut-over is stated on the
> page. Then migration `0010` extending the `indicators.topic` CHECK with
> `disaster` (same shape as `0007`); five indicators — `DISASTER_INCIDENTS`,
> `DISASTER_DEATHS`, `DISASTER_INJURED`, `DISASTER_AFFECTED_FAMILIES`,
> `DISASTER_ECONOMIC_LOSS_NPR` — at YEAR grain, at district + province +
> country, with `{"hazard": "<group>"}` breakdowns, computed by the loader and
> never derived at request time. Wire `ChoroplethMap`, `HeadlineChart`,
> `SparkCard` and `SeasonalityPanel` to them, and adopt the three orphan World
> Bank indicators `EN_CLC_DRSK_XQ`, `EN_CLC_MDAT_ZS`, `VC_IDP_NWDS` into the
> sector via `extraCodes`.

**VERIFICATION:** deaths in the loaded archive reconcile against a direct count
over the source XML (**32,758** for the whole file) · the yearly series is
continuous 1971→today with no missing year · totals for one district in one year
match a hand query over `disaster_incidents` · gates green.

### DIS.S4 — Live river and rainfall status

> **ACTIONS.** `/v1/rivers/status` and `/v1/rain/status` as request-time
> proxies with a strict server-side timeout (reuse the `anyio.fail_after`
> pattern in `api/access.py`), returning **503 on upstream failure — never a
> stale value presented as current**. `RiverStatusPanel.tsx` showing level
> against warning and danger, with a visible "as of HH:MM". The existing
> `no-store` middleware is already correct for live data; change nothing there.

**VERIFICATION:** panel values match bipadportal.gov.np at the moment of
checking · the 503 path is exercised by simulating a timeout · gates green.

### DIS.S5 — Keeping it current

> **ACTIONS.** A `bipad` job in `.github/workflows/ingest.yml`, daily,
> incremental by `incident_on__gt`, recomputing aggregates for the last two
> years to catch late corrections. It must fail loudly and publish nothing
> partial when BIPAD is unreachable. Incidents into `/v1/search`; bounded CSV
> export of the feed.

**VERIFICATION:** `workflow_dispatch` dry-run · a simulated outage leaves the
previous data intact · gates green.

### DIS.S6 — Optional: USGS earthquakes, and an alert banner

1,360 events M4+ since 1900 as a second point layer, and a data-driven banner
from `/alert/`. Valuable, not required.

### DIS.S7 — Deferred

ReliefWeb once an `appname` is registered · ICIMOD glacial lakes if the data
proves downloadable · EM-DAT as an outbound link only.

---

## Storage budget

Live database **247 MB of 500 MB** after DIS.S1. At ~420 bytes per event row
including indexes:

| Part | Rows | Estimate |
|---|---|---|
| BIPAD incidents | 63,151 (measured) | ~27 MB |
| DesInventar 1971–2010 | ~18,500 | ~8 MB |
| USGS | 1,360 | <1 MB |
| Yearly aggregates | ~33,000 | ~13 MB |
| **Total** | | **~48 MB → ~295 MB of 500** |

If a load lands over budget, drop in this order: narrow the event columns and
keep the full payload in the raw lake only; keep only events with a non-zero
impact; shorten the point-mapped window. **Never drop the aggregates** — they
are the cheap part that makes everything else searchable.

---

## Risks

- **Boundary change** — the 2015 restructuring is the largest source of silent
  error. The crosswalk plus loud rejection is the guard.
- **Revised death tolls** — BIPAD corrects counts after the fact. Say so on the
  incident view rather than hiding it.
- **Upstream availability** — the live panel degrades to "unavailable"; the
  archive and the map are stored, not proxied, so they are unaffected.
- **Sensitivity** — these records are deaths. Presentation stays factual and
  restrained: no animated death counters, no league table of districts by
  tragedy.
