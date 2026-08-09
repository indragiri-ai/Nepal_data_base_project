# Election Commission of Nepal — provenance and channel notes

Covers **ECN.S1** (channel recon) and **ECN.S3** (the load) —
`docs/steps/onboard-election-commission.md`. Everything below was verified live
on **2026-08-09**. Anything not verified is marked as such — and there is a
section for it, because the most useful finding of the spike is what the portal
does *not* serve.

    make ecn-probe   re-run the recon, regenerate reference/ecn/inventory.json
    make ecn-load    load the results (idempotent; a re-run writes nothing)

Machine-readable companion: `reference/ecn/inventory.json` (every path probed,
its HTTP status, size and row count).

## What this source is

The **Election Commission of Nepal** is the constitutional election authority,
so this is a **first-party source** — the results are not a re-publication of
anyone else's numbers. Attribute as "Election Commission of Nepal".

**Licence: none stated.** The portal publishes no licence text of any kind.
These are official public records of a state body; we attribute clearly and
record here that no licence was published, rather than assuming one.

## The channel

    https://result.election.gov.np/Handlers/SecureJson.ashx?file=<path>

The site looks like a 2010-era ASP.NET application and its pages are shells:
every figure a visitor sees arrives afterwards from that one handler, as
ordinary JSON. **The whole portal is machine-readable, and no browser is ever
needed** — which is what we most wanted to know, because a pipeline that
depends on driving a browser breaks the first time a page is restyled.

### The four things a request must carry

Found by elimination; miss any one and the answer is `403 Forbidden`:

1. **a session** — GET `/` first, which sets `ASP.NET_SessionId` and `CsrfToken`
   cookies;
2. **`X-CSRF-Token`** — echoing the `CsrfToken` cookie. The site's own script
   reads it straight back out of `document.cookie`
   (`JSLibrary/Common.js`, `getCsrfToken`), so it is handed to every anonymous
   visitor unprompted;
3. **a browser `User-Agent`** — curl's and python-requests' defaults are refused;
4. **a `Referer`** on the portal's own host.

This is a same-origin nuisance filter on public pages, not an access control,
and `ingestion/election/ecn_client.py` simply behaves the way the portal's own
page behaves.

### Rate limiting — the portal enforces its own pace

At a 0.8-second pause the first run was throttled after roughly 70 requests:
**fifteen consecutive `429 Too Many Requests`**, then service resumed. The pause
is now **2.0s** with a 30/90/180-second backoff.

The important part is not the delay. **A 429 is served as an HTML body, exactly
like a missing file**, so the first run recorded fifteen districts as having no
data and then reported that the district totals did not reconcile with the
national total — blaming the ECN for our own truncated read. The client now
raises `EcnThrottled` rather than ever returning a throttle as an absence, and
the probe checks district *coverage* before it checks district *arithmetic*.

### Encoding

Some payloads are UTF-8 **with a BOM** (the district lookup is), which
`json.loads` rejects outright. Everything is decoded `utf-8-sig`. All names are
Devanagari — `configure_stdout_utf8()` is mandatory in every entrypoint.

---

## What the portal serves

### Elections available

| Election | BS year | What is served | Paths |
|---|---|---|---|
| House of Representatives | **2082** | FPTP + PR, full | `Election2082/…`, `ElectionResultCentral2082.txt` |
| House of Representatives | **2079** | FPTP + PR, full | `Election2079/…`, `ElectionResultCentral2079.txt` |
| Provincial Assemblies | **2079** | FPTP + PR | `Election2079/PA/…`, `ElectionResultState2079.txt` |
| By-elections | 2079, 2080, 2081 | candidate results | `ElectionResultCentral2079bi.txt`, `JSONFiles/BIElection/…` |
| National Assembly | 2080 | page exists | `/NA2080.aspx` — not yet mined |
| Local level | 2079 | page + lookups exist | `Election2079/Local/…` — not yet mined |

`Election2074/…` and `Election2081/…` **404**. The 2074 (2017) general election
is reachable only through `/BiElectionFPTPMapBasedResult.aspx`, which is a
by-election map, not the general result — so **the 2017 general election is not
available through this channel** and would need the ECN's published result books.

### The data families, per cycle

| Family | Path template | Granularity | Rows |
|---|---|---|---|
| PR party votes, national | `Election{cycle}/Common/PRHoRPartyTop5.txt` | national | one per party |
| PR party votes, **by district** | `Election{cycle}/HOR/PR/District/{districtCd}.json` | **77 districts** | one per party |
| PR party votes, by province | `Election{cycle}/HOR/PR/Province/{stateId}.json` | 7 provinces | one per party |
| PR party votes, by constituency | `Election{cycle}/HOR/PR/HOR/HOR-{d}-{c}.json` | 165 constituencies | one per party |
| FPTP seats by party | `Election{cycle}/Common/HoRPartyTop5.txt` | national | one per party |
| FPTP winners | `Election{cycle}/Common/HOR-T5Winner.json` | constituency | one per seat |
| FPTP full candidate results | `ElectionResultCentral{cycle}.txt` | constituency | **every candidate** |
| FPTP by constituency | `Election{cycle}/HOR/FPTP/HOR-{d}-{c}.json` | constituency | one per candidate |
| Province / district lookups | `Election{cycle}/Local/Lookup/{states,districts}.json` | — | 7 / 79 |
| Constituency lookup | `Election{cycle}/HOR/Lookup/constituencies.json` | district | 78 |

The path templates are not guesses: they are copied out of the portal's own
`/Scripts/MapElectionResult.js` and `/Scripts/PRMapElectionResult.js`, which
build them from an `ElectionYear` observable.

The **district-level PR file is the prize**: 77 files per cycle give a real
choropleth of party support, which is what ECN.S4's map needs.

---

## What the portal does NOT serve — read this before starting ECN.S2

**There are no registered-voter or turnout figures for either general
election.** This was searched for properly, not assumed:

- every candidate row carries `TotalVoters` and `CastedVote`, and both are
  **`0` in every row of every file**, in both cycles;
- the fields the map page's own code expects — `MVoters`, `FVoters`, `OVoters`,
  `TVoters`, `CastedVote`, `ValidVote`, `InvalidVote` — are **absent entirely**
  from the general-election files;
- those fields *are* populated, and correctly, in
  `JSONFiles/BIElection/VoteCountHORPA.txt` — but that file covers **four
  by-election constituencies**, nothing more;
- the plausible file names for a general-election equivalent were probed and all
  404 (recorded in `inventory.json` under "absent").

**Consequence for ECN.S2** (`ELECTION_VOTERS_REGISTERED`, `ELECTION_TURNOUT_PCT`):
this portal cannot supply them. S2 needs a different channel — the ECN's own
published voter statistics or its post-election report. Until such a channel is
verified, the honest district-level measure this portal *can* support is
**valid PR votes cast per district**, which is a real published number and
should be labelled as such — never as "turnout", which it is not, because the
denominator is missing. **Founder's decision 2026-08-09: S2 deferred; the
dashboard uses votes cast.**

### A lead for whenever turnout is picked up again

Found while establishing the election dates, and recorded here so the search
does not start from nothing. The main site's notice feed
(`https://election.gov.np/admin/public/api/resources/notice?page=N`, 30 pages,
298 notices, plain JSON) carries this for the **2079** election:

    2022-09-17  मतदाता, मतदान स्थल र मतदान केन्द्र संख्या
                (प्रदेश / जिल्ला / प्रतिनिधि सभा नि.क्षे. / प्रदेश सभा नि.क्षे. अनुसार)
    -> .../storage/HoR/Notice/अन्तिम नामावली सम्बन्धी विवरण.pdf

i.e. **voters, polling places and polling-centre counts by province, district
and constituency** — the registered-voter denominator, published a month before
polling. It is a **PDF**, so it needs the staging + human review route, and it
is registration at that date rather than a turnout numerator. No equivalent was
located for 2082. **Not verified, not opened, not ingested** — it is a lead, not
a fact.

---

## Defects in the source (found, pinned by tests, not worked around silently)

**1. The district lookup contains two phantom districts.** It returns 79 rows
for Nepal's 77 districts: ids **98 and 99**, both named `"NA"`, both with no
province. Left in, they become two empty districts in every join.
`real_districts()` drops exactly these two and the count is asserted at 77.

**2. The constituency lookup lists district 77 twice.** Both rows say 2 seats,
so a naive sum gives **167 seats for a 165-seat house**. Summing over *distinct*
district codes gives 165, the constitutional number. Pinned by
`tests/test_ecn_probe.py`.

**3. The "2082" provincial PR files are the 2079 data, with rows duplicated.**
This one is worth stating exactly, because it would be invisible on a chart.
`Election2082/Common/PRPAPartyTop5-S{1..7}.txt` are served under the 2082 path
but contain the previous election's numbers:

- for province 1, **all 36 distinct (party, votes) pairs in the 2082 file are
  identical to the 2079 file** — not similar, identical; **zero** rows are
  unique to 2082;
- the file has 38 rows for those 36 parties: the UML and Nepali Congress rows
  each appear **twice**, with the same vote total under two different symbol
  ids (1 and 2). That inflates the province's total from the 2079 figure of
  1,899,144 to 3,127,560 — exactly 1,899,144 + 665,460 + 562,956;
- the seven provinces then sum to **16,090,350**, larger than the entire
  national PR vote of 10,835,025, which is arithmetically impossible for one
  electorate.

**Not ingested, and not to be ingested.** The 2079 originals are clean
(36 rows, 36 parties, no duplicates).

There is a plainer reading behind this: the 2082 election appears to have been
for the House of Representatives alone, so there is no 2082 provincial result
for these files to hold — but a stale copy is being served rather than nothing.
Whether provincial assemblies were contested in 2082 is **not established
here** and must be verified from an ECN publication, not inferred from a file
layout.

---

## The 2082 BS House of Representatives election — parsed

165 FPTP constituencies, 3,405 candidate rows, 57 parties on the PR ballot.
**Total valid PR votes counted: 10,835,025.**

| PR votes | Share | Party |
|---:|---:|---|
| 5,183,493 | 47.84% | राष्ट्रिय स्वतन्त्र पार्टी |
| 1,759,172 | 16.24% | नेपाली काँग्रेस |
| 1,455,885 | 13.44% | नेपाल कम्युनिष्ट पार्टी (एकीकृत मार्क्सवादी लेनिनवादी) |
| 811,577 | 7.49% | नेपाली कम्युनिष्ट पार्टी |
| 385,902 | 3.56% | श्रम संस्कृति पार्टी |

| FPTP seats | Party |
|---:|---|
| 125 | राष्ट्रिय स्वतन्त्र पार्टी |
| 18 | नेपाली काँग्रेस |
| 9 | नेपाल कम्युनिष्ट पार्टी (एकीकृत मार्क्सवादी लेनिनवादी) |
| 8 | नेपाली कम्युनिष्ट पार्टी |
| 3 | श्रम संस्कृति पार्टी |
| 1 | राष्ट्रिय प्रजातन्त्र पार्टी |
| 1 | स्वतन्त्र (independent) |

## The 2079 BS House of Representatives election — parsed

2,411 candidate rows, 47 parties on the PR ballot.
**Total valid PR votes counted: 10,560,082.**

| PR votes | Share | Party |
|---:|---:|---|
| 2,845,641 | 26.95% | नेपाल कम्युनिष्ट पार्टी (एकीकृत मार्क्सवादी लेनिनवादी) |
| 2,715,225 | 25.71% | नेपाली काँग्रेस |
| 1,175,684 | 11.13% | एकल चिन्ह … (नेकपा (माओवादी केन्द्र) / नेपाल समाजवादी पार्टी) |
| 1,130,344 | 10.70% | राष्ट्रिय स्वतन्त्र पार्टी |
| 588,849 | 5.58% | राष्ट्रिय प्रजातन्त्र पार्टी |

| FPTP seats | Party |
|---:|---|
| 57 | नेपाली काँग्रेस |
| 44 | नेपाल कम्युनिष्ट पार्टी (एमाले) |
| 18 | नेपाल कम्युनिष्ट पार्टी (माओवादी केन्द्र) |
| 10 | नेपाल कम्युनिष्ट पार्टी (एकिकृत समाजबादी) |
| 7 | जनता समाजवादी पार्टी, नेपाल |

Note the 2079 PR ballot's **joint symbol**: two parties contested the
proportional vote under one symbol and the portal reports them as a single
combined row. It cannot be split, and must not be split by us — it is stored and
labelled exactly as published.

### Verified independently against the ECN's own rendered page

The numbers above were parsed from the JSON handler. They were then checked a
second way — by loading `PRVoteChartResult2082.aspx` in a browser and reading
what a visitor actually sees. The page prints Nepali numerals; every one
matched:

    जम्मा मत: १,०८,३५,०२५   = 10,835,025   (our total)
    राष्ट्रिय स्वतन्त्र पार्टी  ५१,८३,४९३  = 5,183,493
    नेपाली काँग्रेस         १७,५९,१७२  = 1,759,172
    नेपाल क.पा. (एमाले)    १४,५५,८८५  = 1,455,885

### The status of these figures — the ECN's own caveat

The page carrying them is titled **"मतगणना प्रगतिको विवरण"** — *details of
vote-counting progress* — and subtitled *"consolidated details prepared on the
basis of what has been entered into the system from counting centres across the
country"*. Its footnote states that the **official** record is the one certified
by the relevant Chief Election Officer / Election Officer's office.

So this portal is the Commission's **operational consolidation, not the
certified legal record**. The count itself is finished — no seats sit in
`TotLead` in either cycle, and the seats reconcile to 165 — but the distinction
is the source's own, and it must travel with the data: any chart built from this
should say it shows the Election Commission's published count, and should not
claim to be the certified result.

### The polling dates — established from ECN documents (ECN.S3)

The results portal names its elections by **BS year only** (`निर्वाचन, २०८२`) and
states no polling date anywhere in the data. Rather than guess, both dates were
taken from the Commission's own publications and converted with this project's
BS calendar (`ingestion/common/bs_calendar.py`), which is itself authoritative
reference data:

| Election | The document | What it says | Gregorian |
|---|---|---|---|
| **2082 BS** | Call for international observers, published 28/10/2025 (`storage/Observer2082/ObserverNotice_Int.jpeg`, on ECN letterhead with its seal) | *"House of Representatives Election, 2026" of Nepal **being held on 5th March, 2026***  | **Thu 5 March 2026** = 2082-11-21 BS |
| **2079 BS** | Official election programme (`storage/HoR/Notice/FPTP निर्वाचन कार्यक्रम.xlsx`) — the FPTP sheet and the PR sheet agree | मतदान (polling) = **2079-08-04 BS** | **Sun 20 November 2022** |

Two notes worth keeping:

- The main site's navigation labels the 2082 election **"Federal Election 2025"**,
  which contradicts the Commission's own notice calling it the *House of
  Representatives Election, 2026*. The dated notice is the better evidence and is
  what we use; the menu label appears to be an error on their site.
- The surrounding notices corroborate March 2026 independently: polling-centre
  lists on 25 February 2026, PR seat allocation on 12–13 March 2026, and the
  declaration of elected PR candidates on 16 March 2026.

These dates are pinned by a test and live in `ELECTIONS` in
`ingestion/election/ecn_pipeline.py`. The calendar year of each is what separates
the two elections in the warehouse.

---

## Cross-checks run (the source asked to agree with itself)

Comparing to a press-release figure we have not verified would be guessing, so
the checks are internal:

- **coverage** — a PR file read for all 77 districts (this check exists because
  of the 429 incident above, and runs *before* any arithmetic);
- **district PR sums to national PR**, in total and party by party;
- **candidates marked `Elected` reconcile with the portal's own seat chart**;
- **FPTP seats total 165**;
- **the constituency lookup is internally sound** (one row per district; 165
  seats over distinct districts).

**Result of the run on 2026-08-09 — 12 of 14 checks passed, for both cycles:**

- 77 of 77 district PR files read, both cycles;
- district PR votes sum to the national total **exactly**, difference **0**, in
  both cycles — 10,835,025 (2082) and 10,560,082 (2079) — and every individual
  party's district votes reconcile to its national figure;
- 165 candidates marked `Elected` against 165 seats in the portal's own chart,
  both cycles;
- the two failures are both the **known duplicate district row** in the
  constituency lookup (defect 2 above), which is handled and pinned by a test —
  not a data problem in the results themselves.

The full machine-readable record — 171 paths probed, 166 served — is in
`inventory.json`. Raw archive of the run:
`ecn/results/2026-08-09T080828_193057Z/probe.json` (166 payloads, 11,252,709
bytes, sha256 `8bc5a9826483931e…`).

---

## What ECN.S3 actually loaded (2026-08-09)

Two indicators, both under topic `governance`, loaded by `make ecn-load`
(`ingestion/election/ecn_pipeline.py`):

| Indicator | Geography | Breakdowns | Unit |
|---|---|---|---|
| `ELECTION_VOTES_PR` | national + all **77 districts** | `{party}` | VOTES |
| `ELECTION_SEATS` | national | `{party, system:'fptp'}` | SEATS |

for both elections, keyed to the calendar year of polling (2026 and 2022).

**8,132 observations loaded** under release 51 on 2026-08-09, and verified by
querying the warehouse afterwards rather than trusting the loader's own report:

| Indicator | Year | Level | Rows | Sum |
|---|---|---|---:|---:|
| `ELECTION_VOTES_PR` | 2026 | country | 57 | 10,835,025 |
| `ELECTION_VOTES_PR` | 2026 | district | 4,389 | **10,835,025** |
| `ELECTION_VOTES_PR` | 2022 | country | 47 | 10,560,082 |
| `ELECTION_VOTES_PR` | 2022 | district | 3,619 | **10,560,082** |
| `ELECTION_SEATS` | 2026 | country | 7 | 165 |
| `ELECTION_SEATS` | 2022 | country | 13 | 165 |

The district rows sum to the national figure **exactly, in the warehouse**, for
both elections — the check is not only a pre-flight assertion. Raw archive of
the load: `ecn/results/2026-08-09T105114_001251Z/load.json` (3,545,453 bytes).

**Idempotent, proven by re-running it**: the second run rebuilt all 8,132
observations, found all 8,132 unchanged, and wrote **nothing**.

**The load refuses to run unless the source reconciles.** These are not warnings
— each raises and nothing is written: 77/77 district files read; district votes
summing to the national total, in total *and* party by party; FPTP seats
totalling 165; no duplicate party in the national PR file. The coverage check
comes first, so a truncated read can never be reported as a source that fails to
add up (the mistake ECN.S1's first run made).

### Two deliberate gaps — say these out loud rather than paper over them

1. **`ELECTION_SEATS` holds constituency seats only.** The 110 proportional
   seats are allocated in a separate ECN notice (for 2082: the notices of
   12–13 March 2026), not through the results portal. A party's number here is
   its **FPTP seats**, never its total in the 275-member house. Any chart must
   say so, or it will understate every large party.
2. **English party names are mostly blank** in `party_names.csv`. Of the **91**
   party names across both elections, the Commission itself publishes an English
   name for only **7**, in its by-election feed (`PoliticalPartyNameEng`); **84**
   await curation. We do not transliterate: an invented English name for a
   political party looks official and is not.

   Every English name carries `source_of_english` saying where it came from.
   That column is **preserved, never re-derived** on a rewrite — an early
   version of the loader recomputed it and so relabelled all seven
   ECN-published names as "curated by hand" on the second run, asserting a human
   check that had never happened. Pinned by a test.

## The 2079 local election — all 35,221 seats

Nepal's local election of **13 May 2022** (2079-01-30 BS, from the Commission's
own sealed election programme published 2022-03-24) filled every seat in the 753
local governments. The portal publishes a per-office summary at

    JSONFiles/Election2079/Local/TopFivePartyPostWise<Office>.json

for eight offices, and `ELECTION_LOCAL_SEATS` loads all of them (40 rows):

| Office (Nepali) | English | Seats | Won |
|---|---|---:|---:|
| प्रमुख | Mayor (municipality) | 293 | 293 |
| अध्यक्ष | Chair (rural municipality) | 460 | 460 |
| उपप्रमुख | Deputy mayor | 293 | 293 |
| उपाध्यक्ष | Deputy chair | 460 | 460 |
| वडा अध्यक्ष | Ward chair | 6,743 | 6,743 |
| महिला सदस्य | Woman member | 6,743 | **6,742** |
| दलित महिला सदस्य | Dalit woman member | 6,743 | **6,620** |
| सदस्य | Member | 13,486 | 13,486 |
| | **Total** | **35,221** | **35,097** |

The English office names come from the Commission's **own file names**, not from
a translation of ours.

**124 seats were never filled** — 123 Dalit woman member seats and 1 woman
member seat. That is a real published outcome about Nepali local democracy, so
the loader reports it and the page states it. Seats won *below* seats available
is therefore not an error; seats won *above* is impossible and blocks the load.

### Two limits of the local data — both stated on the page

**1. Only four parties per office, plus "अन्य".** The files live up to the name
`TopFive…`: four named parties and one combined **अन्य (Other)** row at rank 50.
The totals are complete, but individual small parties and independents cannot be
separated. There is no fuller variant — `PartyPostWise…`, `AllPartyPostWise…`
and `TopTenPartyPostWise…` were all probed and all 404.

**2. A cross-office total is only valid for a party itemised in EVERY office.**
This is the subtle trap in the format, and it is easy to publish a wrong number
here. A party listed for mayors but not for members has its member seats folded
into अन्य, so adding up the rows where it *does* appear understates it badly.
In 2079 only **three parties plus अन्य** are itemised for all eight offices:

    नेपाली काँग्रेस 13,773 · नेपाल क.पा. (एमाले) 11,929
    नेपाल क.पा. (माओवादी केन्द्र) 5,045 · अन्य 2,798

One party is itemised for **a single office**: summing its rows gives 12 seats
nationally, which would be plainly wrong. The panel therefore totals only the
parties present in every office and names the rest as uncountable.

### The two result files name the same party differently — do NOT join them

Found while building ECN.S4, and it is the sharpest trap in this source. The
Commission publishes the seat table and the proportional-vote table with
**different names for the same party**:

    seats  (2079)   नेपाल कम्युनिष्ट पार्टी (एमाले)
    votes  (2079)   नेपाल कम्युनिष्ट पार्टी (एकीकृत मार्क्सवादी लेनिनवादी)

Joining the two on the party name therefore produced **"0 seats" for a party
that won 44** — a wrong number, which is worse than an absent one. Some seat
names also carry trailing whitespace.

**And it cannot be repaired by tidying the strings.** In 2079 two parties
contested the proportional ballot under a single joint symbol and are published
as one row; no seat figure belongs to it. The relationship the source supports
is "here are the votes" and "here are the seats", not "this party's votes and
seats". The portal shows them as two separate charts and two separate tables,
says why on the page, and joins neither. A future step that wants the join needs
a curated party-identity mapping, reviewed by a human — the same treatment
`party_names.csv` gets.

### New units

`VOTES` and `SEATS` were added to `db/seeds/units.csv` rather than reusing
`COUNT`. A vote total is not a count of people — one voter casts both an FPTP
and a PR ballot — and a seat total has a fixed constitutional denominator, which
is what makes it checkable.

### District mapping — curated, not computed

`db/seeds/ecn_district_codes.csv` maps the ECN's district codes to our
geography codes, one row per district, each carrying its evidence:

- **72** matched the Commission's Devanagari district name **exactly**, within
  the correct province;
- **5** were resolved by a human and say why in the `how_matched` column. All
  five differ only in spelling, not identity: तेर्हथुम/तेह्रथुम (र्ह↔ह्र),
  बर्दघाट/वर्दघाट and कपिलवस्तु/कपिलबस्तु (ब↔व), बागलुङ/बाग्लुङ्ग and
  दाङ/दाङ्ग (halant placement).

The ECN's numbering does **not** line up with our codes (their 45 is Nawalparasi
East = `NP0447`, their 50 is Baglung = `NP0443`), so there is no numeric
shortcut and none is attempted. A district code absent from this file raises
rather than being skipped — a silently dropped district is a hole in the map.

## Binding policies for this source

Restated here because they govern every later step, and the step file is easy
to lose sight of once implementation starts.

**Privacy — no individual-level voter data, ever.** `voterlist.election.gov.np`
holds the voter roll. We never ingest it. Only aggregate counts the ECN itself
publishes.

**Candidates are public figures; their personal details are not our business.**
The candidate result files carry `FATHER_NAME`, `SPOUCE_NAME`, `DOB`, `ADDRESS`,
`QUALIFICATION` and citizenship district for every candidate. **These are not to
be ingested or republished.** What we take is the result: constituency, party,
votes, and whether elected. The rest is personal data that being technically
reachable does not make ours to redistribute.

**Final published results only.** Never scrape a live count. Both cycles here
are settled: no seats sit in `TotLead` in either seat chart, which is what a
finished count looks like.

**Neutral presentation.** Parties ordered by votes or alphabetically. **Never
party brand colours** — the portal's own validated categorical palette, with
parties beyond the cap folded into "Other" per the dataviz series-cap rule.
Every chart cites the Election Commission of Nepal and the election's full name.

**Party names exactly as published.** Devanagari as primary, stored verbatim. An
English transliteration belongs in a curated CSV reviewed by a human
(`reference/ecn/party_names.csv`, ECN.S3) — never auto-transliterated.
