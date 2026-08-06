# Open Data Nepal — provenance and channel notes

Source onboarded from ODN.S1 (`docs/steps/onboard-opendatanepal.md`).
Everything below was verified live on **2026-08-06** with
`make odn-probe`; anything not verified is marked as such.

## What this source is

**An aggregator, not an origin.** Open Data Nepal is a CKAN portal run by the
Open Knowledge Nepal community, re-publishing datasets from government
agencies. Authority belongs to the publishing agency; ODN is the distribution
channel. So for anything loaded from here:

- `sources` row = the **originating agency**
- `datasets` row = the **ODN dataset** (`access_method = api`), with the
  agency's own URL recorded in the notes

## The channel

    https://api.opendatanepal.com/api/3/action/{package_show,package_search,datastore_search}

No auth for reads. `datastore_search` pages via `limit`/`offset` and reports
`total`, which is what makes a complete-or-fail harvest possible. Confirmed
working 2026-08-06.

**TLS note:** the API's certificate chain is rejected by an out-of-date CA
bundle — a stale system Python failed with `CERTIFICATE_VERIFY_FAILED`
(certificate has expired) while `curl` and the project venv (certifi
2026.05.20) both succeeded. Nothing to fix in this project; worth knowing
before someone debugs the wrong thing.

## Kalimati Tarkari Market dataset (T1) — verified 2026-08-06

    dataset : kalimati-tarkari-dataset
    agency  : Kalimati Fruits and Vegetable Market Development Board
    licence : cc-by (Creative Commons Attribution)  — open, no sign-off needed
    origin  : https://kalimatimarket.gov.np/ (named in the dataset notes)
    modified: 2026-06-15

Two datastore-active resources, **242,411 rows in total**.

### Resource 1 — `b791b8cd-7ed4-445c-ad8d-69bf58a2c8d4` — clean

    197,161 rows · 2013-06-16 → 2021-05-13
    fields: _id, SN, Commodity, Date, Unit, Minimum, Maximum, Average

The step file's facts-bank sample reproduces **exactly**: row 1 is
`Tomato Big(Nepali), 2013-06-16, Kg, 35.0, 40.0, 37.5`. That row is pinned by
a test against a captured fixture, so a re-upload with different content
fails rather than passing as the same data.

### Resource 2 — `1095e921-51ae-47b7-a501-9da185c0644e` — MALFORMED

**Two corrections to the step file's facts bank, both found by probing:**

1. **The coverage is not "May 2021 → present".** The resource title says
   *"May 2021 to September 2023"*, and its first row is dated **2021-01-05**.
   So the dataset as a whole is a **closed historical series ending in 2023**,
   not a live daily feed. The step's framing of Kalimati as "2013→present,
   maintained" is wrong on the data even though the ODN *metadata* was touched
   in June 2026. Anything published from this must state the window and must
   never be presented as current prices — the step's own vintage-honesty rule.

2. **The column names are wrong at source.** The CSV was uploaded without a
   header row, so CKAN took its first DATA row as the header. The fields are
   literally:

       _id, "Tomato Big(Nepali)", "2021-01-05 00:00:00", "Kg", "50", "60", "55"

   and the first data row reads
   `{"Tomato Big(Nepali)": "Tomato Big(Indian)", "2021-01-05 00:00:00":
   "2021-01-05T00:00:00", "Kg": "Kg", "50": 50, "60": 60, "55": 55}`.

   The positions still line up with commodity / date / unit / min / max / avg,
   and the header row itself is a real observation that has been eaten by the
   upload. **That mapping is not adopted here.** It is a decision for the
   loader (ODN.S2), and it must be *verified* — against
   kalimatimarket.gov.np's own published prices for the same dates — before
   45,250 rows are read through an assumption. Guessing it would be exactly
   the failure rule 1 exists to prevent.

The CKAN client deliberately passes these field names through untouched: a
generic client that silently renamed them would hide the fault from the only
code able to check it.

## Open decisions for ODN.S2

- Whether to load resource 2 at all, and if so under what verification of the
  positional mapping. Resource 1 alone gives a clean 2013→2021 daily series.
- Basket size and storage. 242,411 source rows, filtered to Kg-only and a
  top-25 commodity basket across three statistics, is a large load for a free
  tier. The step requires a projected-size check with a **STOP** at 200 MB.
