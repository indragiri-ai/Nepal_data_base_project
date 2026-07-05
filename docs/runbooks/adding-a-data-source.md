# Runbook — Adding a new data source

**Purpose:** the repeatable checklist for onboarding ANY new source (API, Excel,
PDF, manual) into the portal. Following it means a new source is *one adapter +
some reference data*, never a database redesign.

**Governing principle (Blueprint §2.1):** the warehouse (`observations` + the
dimension tables) never changes for a new source. Each source gets an **adapter**
under `ingestion/<source>/` that maps its quirks into the universal model:
*indicator × geography × time period (× breakdowns) = value*.

**UTF-8 rule (carry-forward Lesson 1):** every entrypoint script MUST call
`configure_stdout_utf8()` from `ingestion.common.io_utf8` before it prints —
the Windows console defaults to cp1252 and crashes on Devanagari.

---

## The layered flow every source follows

```
SOURCE → [raw lake] → [parse] → [staging + review]? → [quality gate] → warehouse (observations)
```

- **Raw lake** — store the original payload (JSON/XLSX/PDF) *exactly as received*,
  with SHA-256 hash + fetch timestamp + source URL, BEFORE parsing (Blueprint §2.2).
- **Staging + review** — REQUIRED for any human-extracted data (Excel/PDF). Parsed
  rows land in a staging table and pass a human review checklist before promotion.
  Machine-readable APIs with passing automated tests may skip staging (Master Prompt §3.3, §5.4).
- **Quality gate** — automated checks run *in* the pipeline (ranges, FK resolution,
  no non-numeric values). A failure blocks promotion and is logged (Master Prompt §3.3).
- **Warehouse** — only clean, reviewed, provenance-complete rows reach `observations`.

---

## Onboarding checklist

**1. Register the source (reference data, curated by a human — never invented)**
- [ ] Add a row to `sources` (name, type, url, default license).
- [ ] Add a row to `datasets` with the correct `access_method`
      (`api` / `file` / `scrape` / `manual`) and `documentation_url`.

**2. Map its concepts into our dimensions**
- [ ] For each measure, decide: is it an existing `indicators.code`, or a new one?
      If new, add it with a stable `code`, `topic`, `unit`, and `source_concept`
      (the source's own code). Same real-world concept from two sources stays as
      two datasets feeding the same indicator — they coexist, `preferred_source_id`
      picks the default (Blueprint §4.3).
- [ ] Resolve geographies. Country-level is trivial; sub-national needs the
      `geographies` table and, across the 2015 break, the `geography_crosswalk`
      and `geo_aliases` (Blueprint §5.2). Store data against the boundaries it was
      published in.
- [ ] Resolve time periods. Add any missing `time_periods` rows. Map the source's
      calendar (Gregorian year / BS fiscal year / month / census round) onto the
      period's true Gregorian dates — never to a bare year number (Blueprint §5.1).
- [ ] Identify breakdown dimensions (sex, age, sector, …). These go in the
      `breakdowns` JSONB column; document every key used.

**3. Build the adapter** (`ingestion/<source>/pipeline.py`)
- [ ] Fetch/receive → write raw to the lake (hashed) BEFORE parsing.
- [ ] Parse into observations; skip + count unparseable values (never guess).
- [ ] Create one `releases` row per run (`raw_file_refs` → the stored payloads).
- [ ] For Excel/PDF: load into a **staging table**, run the **review checklist**,
      then promote. For clean APIs: load directly if quality tests pass.
- [ ] Insert under the release; the `is_latest` trigger handles revisions.
- [ ] Write an `ingestion_log` row whether the run succeeds or fails.
- [ ] Make it **idempotent**: re-running produces the same warehouse state
      (guaranteed by the release + uniqueness model).

**4. Quality + tests**
- [ ] Add source-specific quality rules (value ranges, continuity) to the gate.
- [ ] Add a parse test with a saved sample payload (runs offline).
- [ ] Spot-check 2–3 real numbers against the source's own website. They must match.

**5. Close out**
- [ ] `make test` green; commit referencing the step; `PROJECT_LOG.md` entry.

---

## Source-type quick reference

| Type | access_method | Staging/review? | Main gotchas |
|---|---|---|---|
| **API (e.g. World Bank, IMF)** | `api` | No (if tests pass) | Paging; null values |
| **Excel (e.g. NRB bulletins)** | `file` | **Yes** | Layout drift; BS fiscal-year periods; merged cells |
| **PDF (e.g. ministry reports)** | `scrape`/`file` | **Yes** | Extraction accuracy; scanned tables; one parser per layout |
| **Manual upload** | `manual` | **Yes** | Provenance must be recorded by hand |

**Golden rule:** nothing reaches the public portal without passing the review
checklist for its source type. A clean API can flow through automatically; a number
read out of a PDF cannot.
