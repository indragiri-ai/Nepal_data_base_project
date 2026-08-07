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

### Resource 2 — `1095e921-51ae-47b7-a501-9da185c0644e` — MALFORMED, and mis-titled

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

## Verification of the positional mapping — DONE, and it passes (2026-08-06)

Founder's decision: verify the mapping, then load both resources if it holds.
It holds, on two independent tests.

**Test 1 — the overlap (decisive).** The two resources overlap: resource 1
runs to 2021-05-13 and resource 2 starts 2021-01-05, about four months in
common. Reading resource 2 through the positional mapping and comparing it,
commodity by commodity, against resource 1 — whose columns are labelled and
trusted:

| Date | Rows compared | Agree | Disagree |
|---|---|---|---|
| 2021-01-05 | 95 | 95 | 0 |
| 2021-02-14 | 100 | 100 | 0 |
| 2021-03-15 | 108 | 108 | 0 |
| 2021-04-20 | 103 | 103 | 0 |
| 2021-05-13 | 91 | 91 | 0 |
| **Total** | **497** | **497** | **0** |

Unit, minimum, maximum and average all agree exactly. The mapping
`commodity / date / unit / min / max / avg` is confirmed, not assumed.

**Test 2 — the agency's own site (independent channel).** kalimatimarket.gov.np
publishes historical prices through its comparative-prices page (POST with a
CSRF token; Nepali labels, Bikram Sambat dates). For 2022-04-18 the commodity
names line up **exactly by position** with the ODN copy — गोलभेडा ठूलो(नेपाली)
↔ Tomato Big(Nepali), and so on down the list. Identity and ordering confirmed
from outside the aggregator.

### But that test found something else — read before publishing any price

The agency's published average and the dataset's "Average" **disagree for 10 of
24 commodities checked**, always with the agency's higher. The cause is now
established:

> **The dataset's `Average` column is not an average. It is exactly the
> midpoint of that day's minimum and maximum.**

Checked across **5,000 rows sampled from both resources**, spanning the full
2013→2022 range: **100.00% are exactly (min + max) / 2**, zero exceptions. The
agency's own average is a different figure — usually closer to the day's high
(e.g. 2022-04-18, Green Peas: min 60, max 70, our "Average" 65.00, the market
board's published average 66.67).

Consequence for ODN.S2: **the column must not be published as "average
price".** It is a midpoint of the day's range, and that is what a label has to
say. Minimum and maximum are the source's own figures and carry no such
problem.

## Real coverage — a third correction

The resource titles are wrong about the end date too. Verified from the data:

| Resource | Title claims | Actually contains |
|---|---|---|
| 1 | June 2013 → May 2021 | 2013-06-16 → 2021-05-13 ✓ |
| 2 | May 2021 → September 2023 | **2021-01-05 → 2022-04-18** |

So the dataset as a whole covers **2013-06-16 → 2022-04-18** — a decade of
daily prices, ending in April 2022. Not September 2023, and not "present".
Any page publishing it must say so.

Note the agency's own site *does* carry prices past 2022 (2023-09-01 returned
89 commodities), so a future step could extend the series from the market
board directly. That is a different acquisition channel and a separate step.

## The load (ODN.S2) — done 2026-08-07

**153,494 observations**: the daily low and the daily high for each of 25
commodities, 2013-06-16 → 2022-04-18, filed under Kathmandu Metropolitan City
(`NP0327101`), in NPR per kilogram.

| Check | Result |
|---|---|
| Commodity-days loaded | 76,747 (× 2 series = 153,494) |
| Commodities | 25, from `db/seeds/kalimati_basket.csv` |
| Coverage | 2013-06-16 → 2022-04-18, 3,091 trading days |
| Duplicate latest cells | **0** |
| Rows where the low exceeds the high | **0** |
| Value range | 1.0 – 1,500.0 NPR/kg (inside the 0–10,000 band) |
| Spot-checks against the source | **3 of 3 exact** |

Spot-checks span both resources and nine years: Cauli Local on 2013-06-16
(30/35), Potato Red on 2018-07-04 (36/38), Tomato Small(Local) on 2022-04-18
(25/30) — each read back from the warehouse and compared with a fresh API
call.

### The overlap, and the bug it caused

The first load **failed** after 135,000 rows on the
`observations_unique_per_release` constraint. The cause: the two resources
overlap by about four months, and the loader was offering the same
commodity-day twice. The constraint was right to reject it — the alternative
is a silently double-counted price.

The loader now de-duplicates per commodity-day, keeping the later publication,
and reports what it dropped. On the real data: **3,190 duplicate rows dropped,
and every single duplicated commodity-day agreed exactly between the two
resources.** That is a useful result in itself — the two files are consistent
where they overlap, which is further evidence the positional mapping is right.

No data had to be deleted to recover: the loader skips values it already
holds, so the re-run inserted only the missing 18,494 under a new release.

### What the storage actually cost

Projected 76 MB; the real cost was **28.5 MB** (200.3 → 228.8 MB, about 186
bytes per observation). The 476-bytes-per-row figure used for the projection
came from dividing the whole `observations` table and its indexes by row
count, which over-attributes shared index overhead to each new row. The
database now sits at **228.8 MB of the 500 MB free tier (46%)** — considerably
more headroom for future sources than the estimate suggested.

## Still open

- **Extending past April 2022.** The market board's own site publishes later
  prices (2023-09-01 returned 89 commodities), so a future step could continue
  the series directly from the agency. That is a different acquisition channel.
- The remaining 106 commodities outside the basket, and the 6,910 rows priced
  per piece or per dozen, are neither loaded nor lost — they are in the raw
  lake, and a later pass can add them if the storage budget allows.
