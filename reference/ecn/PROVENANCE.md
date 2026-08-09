# Election Commission of Nepal — provenance and channel notes

Source recon from **ECN.S1** (`docs/steps/onboard-election-commission.md`).
Everything below was verified live on **2026-08-09** with `make ecn-probe`.
Anything not verified is marked as such — and there is a section for it, because
the most useful finding of this spike is what the portal does *not* serve.

Machine-readable companion: `reference/ecn/inventory.json` (every path probed,
its HTTP status, size and row count). Regenerate with `make ecn-probe`.

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
denominator is missing.

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

### Dates are NOT yet established

The portal names its elections by **BS year only** (`निर्वाचन, २०८२`). The exact
polling date of each is not stated anywhere in the data we read, and is not
guessed here. **Before either cycle is loaded, the polling date must be verified
from an ECN publication** and recorded in the indicator definition — a period
row must map to real Gregorian dates, never to a bare year (Blueprint §5.1).

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
