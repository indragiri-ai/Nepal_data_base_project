# GLOBAL SEARCH — Step File

**Authored 2026-08-01. Founder-raised gap: the portal holds ~1,400 World Bank
indicators plus the census catalogue and 838 geographies, and there is no way
to search any of it. Verified before writing: a search of `api/` for any query
parameter, `ILIKE`, or Postgres full-text function returns zero matches. There
is no search to improve — there is none.**

Slots into `START-HERE.md` ahead of the remaining source onboardings. Search is
the multiplier on breadth already paid for: every source added afterwards
becomes findable the day it lands, at no extra cost.

---

## Facts bank (verified 2026-08-01 — cite, don't re-derive)

- **The two things worth searching are already modelled.** `indicators`
  (`code`, `name_en`, `name_ne`, `definition_en`, `definition_ne`, `topic`)
  and `geographies` (`code`, `name_en`, `name_ne`, `level`) — both from
  `db/migrations/0002_dimensions.sql`. Nepali columns hold UTF-8 Devanagari.
- **The corpus is small.** Roughly 1,400 + 861 indicator rows and 838
  geographies — on the order of 2,700 rows. A sequential case-insensitive scan
  over 2,700 short text rows is sub-millisecond.
  **Therefore this step adds NO migration, NO index, and NO extension.**
  Storage is the scarce resource (191 MB of the 500 MB tier); spending it on a
  `pg_trgm` index for 2,700 rows would be waste. Revisit only if the catalogue
  grows roughly ten-fold.
- **`to_tsvector` is the wrong tool here and must not be used.** Postgres
  full-text search stems against a language configuration; `'english'` mangles
  Devanagari and there is no Nepali configuration shipped. Character-level
  `ILIKE` matching is script-agnostic and is what makes Nepali search work at
  all. This is the "never guess" rule applied to search: it works in both
  scripts or it is not honest.
- **The API pattern to follow** is `api/repository.py`: a `Repository`
  Protocol, a `PostgresRepository` implementation, frozen dataclass rows, and
  a `FakeRepository` in `tests/test_api.py` so tests run offline.
- **`list_indicators` filters to indicators that have observations** — an
  indicator with no data cannot be charted, so listing it advertises something
  the portal cannot deliver. Search MUST apply the same filter for the same
  reason.
- **The front end already knows how to route an indicator**:
  `sectorForCode(code, topic)` in `web/lib/sectors.ts` returns the owning
  sector. Search results reuse it rather than inventing a second mapping.

---

### SRCH.S1 — One search box that looks in the whole warehouse

**GOAL (plain language):** A visitor types anything — "literacy", "Sarlahi",
"साक्षरता", "GDP" — into one box in the site header and gets back the matching
datasets and places, each one clickable through to where the numbers live.

**WHY IT MATTERS:** Today the only route to the data is clicking sector by
sector. The portal's strongest claim is breadth, and breadth nobody can search
does not read as breadth — it reads as a handful of pages. This is the step
that turns the warehouse into something a visitor can interrogate, and it is
the difference between a demo that answers "do you have X?" with a click and
one that answers it with an apology.

**PREREQUISITES:** none. **TIME:** ~2 hours.

**SCOPE — in:** indicators and geographies. **Out (deliberate, becomes
SRCH.S2):** sources/datasets as their own result kind, typeahead/autocomplete,
fuzzy spelling tolerance, and search over observation values.

**ACTIONS:**

1. **Repository** (`api/repository.py`) — add, no migration:
   - `SearchHitRow` frozen dataclass: `kind` (`"indicator"` | `"geography"`),
     `code`, `name_en`, `name_ne`, `detail` (the indicator's `topic` or the
     geography's `level`), `unit_code` (indicator only, else `None`), `score`.
   - `search(self, term: str, limit: int = 20) -> list[SearchHitRow]` on both
     the `Repository` Protocol and `PostgresRepository`.
   - One `UNION ALL` across indicators and geographies, ordered by score then
     name. Indicators join `units` and keep the
     `WHERE EXISTS (SELECT 1 FROM observations …)` filter.
   - **Escape the user's input before it reaches `ILIKE`.** `%` and `_` are
     wildcards: an unescaped `%` matches the entire catalogue. Escape `\`, `%`
     and `_`, and use `ILIKE … ESCAPE '\'`. A test must cover this.
   - Rank with a `CASE`: exact code match 100 → code contains 80 → name starts
     with the term 60 → name contains 40 → definition contains 20. Search
     `name_en`, `name_ne`, `definition_en` and `code`.

2. **Models** (`api/models.py`): `SearchHit` and `SearchResponse`
   (`query`, `total`, `results`). Mirror them into `web/lib/api.ts`.

3. **Route** (`api/main.py`): `GET /v1/search`.
   - `q` required; `limit` default 20, max 50 (`Query(ge=1, le=50)`).
   - Trim `q`. Fewer than **2** characters after trimming → **422** with a
     plain message. One character matches most of the catalogue and is not a
     search.
   - Never 404 on no matches — an empty `results` list with `total: 0` is a
     valid, honest answer.

4. **Front end:**
   - `SearchBox` client component in the header: a labelled `role="search"`
     form that navigates to `/search?q=…`. Bind `/` to focus it, and make sure
     the key does nothing while the user is typing in another field.
   - `web/app/search/page.tsx` reading `?q=`, grouping results under
     **Datasets** and **Places**, each row showing its name, its Nepali name
     when present, and its topic or level. Indicator rows link via
     `sectorForCode`. For place rows, **read `PopulationDashboard` first** to
     find out whether the map accepts a geography in the URL: if it does, deep
     link to it; if it does not, link to `/population` and record the deep link
     as a follow-up. Do not invent a parameter the page does not read.
   - Empty state names the thing that was searched for and suggests two live
     examples. No results is a normal answer, not an error.

5. **Tests** (`tests/test_api.py`, extend `FakeRepository`) — all offline:
   - matches an English name, case-insensitively;
   - matches a **Devanagari** name (use real Nepali text, e.g. `साक्षरता`);
   - an exact code query ranks that indicator first;
   - `q=%` returns few or no results, proving the escaping (regression test);
   - a one-character `q` returns 422;
   - a no-match query returns 200 with `total: 0`;
   - `limit` is respected and rejects values above 50.

**VERIFICATION CHECKLIST:**
- [ ] `/v1/search?q=literacy` returns census literacy indicators.
- [ ] `/v1/search?q=Sarlahi` returns the district.
- [ ] A Devanagari query returns matches (proves the ILIKE choice was right).
- [ ] `q=%` does not dump the catalogue.
- [ ] Search box reachable and usable by keyboard alone; visible focus ring.
- [ ] Results page renders for a hit, a miss, and a too-short query.
- [ ] No new migration, no new extension, no measurable DB growth.
- [ ] `make lint` clean · `make test` green · `cd web && npm run build` green.

**IF IT GOES WRONG:** Nepali query returns nothing → the column is `name_ne`
and it may be `NULL` for most indicators; confirm with a direct query before
concluding the search is broken, and report that gap rather than faking it.
Slow response → check the observations `EXISTS` filter is not running per row;
at 2,700 rows it should not need an index, and if it does, say so with the
timing rather than adding one on suspicion.

**COMMIT:** `SRCH.S1: global search across indicators and geographies`

---

---

## VERIFIED FINDINGS from the SRCH.S1 build (2026-08-01) — reported, not guessed

Both were measured against the live warehouse, not inferred. Neither is a bug
in the search code; both are gaps in the data underneath it, and both limit
what Nepali search can find today.

**1. Nepali names exist for places, but not for indicators.**

| table | level | rows | with a non-empty `name_ne` |
|-------|-------|------|-----------------------------|
| geographies | country | 1 | 1 |
| geographies | province | 7 | 7 |
| geographies | district | 77 | 77 |
| geographies | local_unit | 753 | **0** |
| indicators | — | 2,252 | **0** |

So a Nepali query today reaches the country, all 7 provinces and all 77
districts, and nothing else. `इलाम` → Ilam and `बागमती` → Bagmati both work.
No municipality and no dataset can be found in Nepali, because the text is not
in the database to match. Filling `name_ne` for the 753 municipalities is a
seed-data task (rule 4: curated by a human in `db/seeds/`, never invented by a
pipeline) — the census source files carry the Nepali municipality names.

**2. Nepali spelling variants do not match each other.**

Kathmandu district is stored as `काठमाडौँ` — with **chandrabindu** (U+0901).
A user typing `काठमाडौं` — with **anusvara** (U+0902) — gets zero results.
Both spellings are in common use. Substring matching compares characters
exactly, so the two forms never meet.

This is a genuine usability gap and is NOT fixed here, deliberately: treating
ँ and ं as interchangeable is a linguistic judgment about Nepali, not a
technical one, and rule 1 says an unverifiable mapping is reported rather than
invented. **This needs a native-speaker decision from the founder** before any
normalization is written. It would be a search-time normalization only — it
would never alter the stored spelling.

---

### SRCH.S2 — Search polish (not this session)

Ordered by value:

1. **Seed `name_ne` for the 753 municipalities** (finding 1) — the single
   biggest increase in what Nepali search can reach.
2. **Decide the ँ / ं question** (finding 2) with the founder. If they are
   interchangeable for search, normalize both the query and the compared
   column at match time.
3. **Deep-link a place result** into `/population`. The map does not currently
   read a geography from the URL, so place hits land on the map root;
   `ExploreDashboard` and `BankingDashboard` already show the pattern for
   accepting a code from the query string.
4. Sources and datasets as a third result kind.
5. Typeahead in the header.
6. Fuzzy matching for misspellings — this is where `pg_trgm` finally earns its
   storage, if the catalogue has grown.
7. Log queries that return nothing: the cheapest possible signal about which
   source to onboard next.
