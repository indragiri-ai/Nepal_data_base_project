# PHASE 5 — LAUNCH & GROWTH — Step File

**Version 0.9 — DRAFT, July 2026**
**Governed by: Master Prompt v1.0 · Architecture Blueprint v1.0**
**Assumes: Phase 4 exit criteria fully met (system self-running and self-reporting, five+ sources live, budgets and restore proven — see docs/steps/phase-4-steps.md and the P4.S12 log entry).**

> **DRAFT STATUS:** The Master Prompt (§4) requires step files to be finalized only when the previous phase nears completion. This draft was written mid-Phase-2 at the founder's request. **Before starting P5.S1: re-read the P4.S12 PROJECT_LOG lessons, fill in the carry-forward section below, adjust any step this invalidates, and bump this file to Version 1.0.**

**Phase goal: put the portal in front of its real audience and make it durable. Audit everything a stranger will judge, add privacy-respecting analytics and feedback channels, soft-launch to researchers and journalists, let their requests drive the dataset queue, publish the first data stories, and write the sustainability plan — then hand the project over from "build phases" to a steady-state operating rhythm.**

**Why now:** Phases 1–4 built a correct, visible, self-running system. But the vision (Blueprint §1) is not a system — it's *people finding data about Nepal*. This phase is deliberately shaped differently: fewer things built, more things learned. Growth decisions from here on are made from real user signals, not guesses. Master Prompt §5 marks this phase open-ended: the steps below are the on-ramp; the loop at the end is the destination.

**Total founder time: ~10–14 hours across 8 steps, then an ongoing monthly rhythm. One step per session. Never two.**
**Phase exit criterion: the portal is publicly announced; at least ten real external users have used it; at least one externally-requested dataset has shipped through the request queue; the sustainability plan is written and adopted; and the steady-state operating loop has completed its first full month. And the P5.S8 checklist passes.**

**How to run every session:** open Claude Code in the project folder, open this file, and tell Claude Code: "We are on step P5.SX of docs/steps/phase-5-steps.md. Follow it under the master prompt." Approve actions one at a time; verify with the checklist; commit; log.

---

## Carry-forward lessons from Phase 4 (apply in every step)

**TO BE FILLED AT P4.S12 CLOSE from the PROJECT_LOG "lessons for Phase 5" entry.** Expected candidates (verify against the actual log; delete what didn't happen, add what did):

1. *(placeholder)* The unattended-week findings: which pipelines needed babysitting and why — launch multiplies whatever was fragile.
2. *(placeholder)* Hosting-tier decisions from P4.S10 (cold starts, budgets) — revisit before announcing publicly.
3. *(placeholder)* The review-queue rhythm: how often staged data actually arrives, so the operating loop's cadence is realistic.
4. *(placeholder — add real lessons from PROJECT_LOG here)*

---

### P5.S1 — Pre-launch audit: everything a stranger will judge

**GOAL (plain language):** Walk the whole public surface the way a skeptical first-time visitor would — every page, every license line, every citation, both languages — and fix what fails, before inviting anyone.

**WHY IT MATTERS:** Blueprint §5.5 (attribute everything, record licenses) and the Quality Bar are about to face outside scrutiny. First impressions with researchers and journalists are not repeatable — the audience this portal most needs is the one most alert to sloppy sourcing.

**PREREQUISITES:** Phase 4 complete; this file bumped to v1.0 with real carry-forward lessons.
**TIME ESTIMATE:** 120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Run a full public-surface audit and report findings as a checklist, honestly: (a) every dataset's license/terms recorded and displayed, every chart/download citing source with a working link (crawl and verify the links); (b) /about accurate and complete — what the portal is, where data comes from, what the review process is, how to contact; (c) both languages complete on all public chrome (the i18n missing-keys report is empty); (d) all suites green against production; (e) no admin/review URL reachable or discoverable publicly; (f) the traceability drill on one number from each source, timed. Fix small findings on a branch; list anything larger for founder triage."
2. Founder does their own pass: 30 minutes clicking as a stranger on a phone — write down everything that feels off, however small.
3. Triage both lists together; fix or log every item (no silent TODOs — §3.7.5).

**VERIFICATION CHECKLIST:**
- [ ] License + working source link verified on every dataset (crawl output attached to the log).
- [ ] i18n report empty; both-language walkthrough done by the founder.
- [ ] Traceability under a minute from each live source; all suites green on production.
- [ ] Every audit finding fixed or logged with a follow-up step — nothing waved through.

**IF IT GOES WRONG:** A license turns out unclear for something already public → take that dataset down until clarified (Prime Directive-level caution); an honest gap beats a quiet liability.

**COMMIT:** `P5.S1: pre-launch audit passed (licenses, citations, bilingual, traceability)`

---

### P5.S2 — Privacy-respecting analytics

**GOAL (plain language):** Add usage analytics that answer "what do people look at, search for, and download?" without collecting personal data — no cookies to consent to, no individuals traceable — plus a founder dashboard of the handful of numbers that matter.

**WHY IT MATTERS:** Master Prompt §5 P5: "usage analytics (privacy-respecting)." Growth decisions (P5.S5's priorities) must come from real usage, and a data-transparency project must hold itself to a higher privacy bar than it holds anyone else. Blueprint §5.5's ethic — no personal data, ever — extends to visitors.

**PREREQUISITES:** P5.S1.
**TIME ESTIMATE:** 90 minutes.

**ACTIONS:**
1. Founder decision: self-hosted vs. hosted privacy-first analytics (Claude proposes 2–3 options — e.g. Plausible/Umami-class — with cost and hosting implications; recommendation included).
2. Instruct Claude Code:
   > "Integrate [chosen tool]: page views by route, search queries (already logged privacy-safely since P3.S6 — unify), download counts by indicator, API usage by endpoint (from cache/host logs, not user tracking). No cookies requiring consent, no IP retention, no fingerprinting — document what is and isn't collected on a public /privacy page linked in the footer. Build a small founder dashboard (or saved views): top indicators, top searches (incl. searches with no results — those are dataset demand signals), downloads, API traffic."
3. Browse the site yourself, then confirm your visit appears in aggregate and nothing identifies you.

**VERIFICATION CHECKLIST:**
- [ ] Analytics live; the founder dashboard shows real events after a self-visit.
- [ ] /privacy page states exactly what is collected; no consent banner is needed because nothing requiring one is collected.
- [ ] No-results searches are captured as a ranked list (the demand signal for P5.S5).

**IF IT GOES WRONG:** The chosen tool quietly wants more data than advertised (IP logs, fingerprinting) → reject it and take the next option; the /privacy page must never say something the stack doesn't do.

**COMMIT:** `P5.S2: privacy-respecting analytics + public privacy page`

---

### P5.S3 — Feedback channels and the dataset request queue

**GOAL (plain language):** Give users a voice before inviting them: a lightweight feedback form, a "request a dataset" form, and a public queue page showing what's been requested and its status — so requests are visibly heard.

**WHY IT MATTERS:** Master Prompt §5 P5: "dataset request queue." The soft launch (next step) asks busy professionals for attention; giving them a visible channel — and visible follow-through — is what converts a visitor into a returning user and an advocate.

**PREREQUISITES:** P5.S2.
**TIME ESTIMATE:** 90–120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Build: (a) a feedback form (page + a small 'was this useful? / report a problem' affordance on indicator pages) storing submissions in a `feedback` table — free text + optional email (clearly optional, used only to reply), no other personal data; (b) a dataset-request form (what data, why, where it's published if known) into a `dataset_requests` table with status (received / investigating / queued / shipped / not-possible + reason); (c) a public /requests page listing requests and statuses — anonymized, no requester info; (d) an authenticated founder view to triage statuses (reuse the review-area auth). Alert me (P4.S3 channel) on new submissions. Both forms bilingual, spam-protected simply (honeypot/rate-limit, not CAPTCHA-with-tracking)."
2. Submit one test feedback and one test request; triage them in the founder view; see the request appear on /requests.

**VERIFICATION CHECKLIST:**
- [ ] Both forms work in both languages; submissions land in the tables and alert the founder.
- [ ] /requests shows the test request with status, no personal data exposed.
- [ ] Status changes in the founder view appear publicly; the not-possible status requires a public reason.

**IF IT GOES WRONG:** Spam after launch → tighten honeypot/rate limits first; never add tracking-based CAPTCHA (contradicts /privacy).

**COMMIT:** `P5.S3: feedback channel + public dataset request queue`

---

### P5.S4 — The soft launch: researchers and journalists

**GOAL (plain language):** Personally invite a hand-picked first audience — 15–30 researchers, journalists, students, and civic-data people — to use the portal, and collect structured first impressions within two weeks.

**WHY IT MATTERS:** Blueprint §7 P5: "soft launch to researchers/journalists for feedback." A small, engaged audience finds the important problems while the blast radius is small — and the master prompt's Quality Bar was written from exactly this user's viewpoint (the journalist in Surkhet).

**PREREQUISITES:** P5.S3. **This step is mostly founder work, not code.**
**TIME ESTIMATE:** 2–3 hours founder time (list-building, personal messages), spread over days.

**ACTIONS:**
1. Build the invite list (founder): people you know or can be introduced to — economics/development researchers, data journalists, university teachers, NGO analysts. Personal messages, not a blast.
2. Instruct Claude Code:
   > "Draft the invite (EN + NE): what the portal is in two sentences, three concrete things to try (one indicator, one map, one download), and where to give feedback (the P5.S3 form). Also draft 3–5 structured follow-up questions for those willing to talk (what did you look for? did you find it? would you cite it? what's missing?). Then prepare a shared tracking note (docs/launch/soft-launch.md, or the founder's tool of choice) for invitees → responses."
3. Send invites in waves (5–10 first — early waves catch problems cheaply). Watch analytics and feedback as responses come in; fix quick issues on branches between waves.

**VERIFICATION CHECKLIST:**
- [ ] 15+ invitations sent personally; tracked.
- [ ] 10+ real external users appear in analytics; 5+ pieces of substantive feedback received (forms or conversations, logged).
- [ ] Any launch-blocking bug found by early waves fixed before later waves.

**IF IT GOES WRONG:** Silence (low response) → the ask was too big or too vague; re-send with ONE concrete task ("look up your district's literacy rate — did you find it in under a minute?"). If a serious data-correctness report arrives: treat as highest priority, verify against the source, and respond personally — a corrected number with a thank-you builds more trust than a portal that was never wrong.

**COMMIT:** `P5.S4: soft launch executed (materials + tracking; fixes on branches)`

---

### P5.S5 — Triage: feedback becomes the roadmap

**GOAL (plain language):** Turn everything learned — feedback, interviews, analytics, no-results searches, dataset requests — into one ranked backlog, and ship the first improvement wave: the top usability fixes plus the most-requested dataset.

**WHY IT MATTERS:** Blueprint §7 P5: "prioritize most-requested datasets." This step establishes the project's permanent growth engine: users signal → founder ranks → proven pipeline patterns deliver. If the Phase 2/4 patterns hold, a requested dataset ships in one session.

**PREREQUISITES:** P5.S4 (2+ weeks of soft-launch signal).
**TIME ESTIMATE:** 120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Aggregate every signal: feedback rows, interview notes, top/no-results searches, dataset_requests, analytics patterns. Produce a ranked backlog in docs/launch/backlog.md grouped as (a) data corrections — always first, (b) usability, (c) requested datasets (with a feasibility note each: source, access method, license, expected effort per our patterns), (d) new features — with your recommendation for this wave. The founder ranks; you don't ship anything from this list without that."
2. Founder ranks; pick the wave: all of (a), the top 2–3 of (b), and the #1 feasible dataset from (c).
3. Ship the wave — the dataset via the standard onboarding runbook + the appropriate pattern (API pipeline or staging/review); mark the request "shipped" on /requests and tell the requester personally.

**VERIFICATION CHECKLIST:**
- [ ] backlog.md exists, ranked by the founder, with feasibility notes on every requested dataset.
- [ ] Zero open data-correction items (fixed and verified against sources, or publicly answered).
- [ ] The #1 requested dataset is live, cited, on /requests as shipped — and the requester was told.
- [ ] Honest note in the log: did the dataset ship in ~one session using existing patterns? If not, what pattern gap did it expose?

**IF IT GOES WRONG:** The most-requested dataset is infeasible (licensing, no published source) → mark it not-possible with the public reason and ship #2; visible honesty about limits is itself a feature.

**COMMIT:** `P5.S5: feedback triaged into ranked backlog; first requested dataset shipped`

---

### P5.S6 — The first data stories

**GOAL (plain language):** Publish 2–3 short data stories — a few paragraphs each around portal charts, e.g. "Nepal's inflation in 5 charts" — that show the portal's value in narrative form and give visitors a reason to arrive and to share.

**WHY IT MATTERS:** Master Prompt §5 P5: "content (data stories)." Raw indicators serve people who already know what to ask; stories serve everyone else, and each one is a durable, shareable demonstration that this data is alive. They also dog-food the chart framework as an embedding consumer.

**PREREQUISITES:** P5.S5.
**TIME ESTIMATE:** 120 minutes (first story + the machinery); later stories are founder-paced.

**ACTIONS:**
1. Instruct Claude Code:
   > "Add a minimal /stories section: markdown-authored posts rendering through the design system, embedding live portal charts by indicator/geo reference (the P3.S5 framework — live charts, not screenshots, every embed citing source), bilingual-capable (a story may launch EN-first with NE to follow, said explicitly), listed on an index page, with social cards. Then draft story #1 from our own analytics: take a top-searched topic and draft 'X in N charts' — five short factual paragraphs, each anchored to a chart, no editorializing beyond what the data shows, every claim checked against the portal's own numbers."
2. Founder edits the draft (the voice must be the founder's) and verifies every number against its chart; publish.
3. Draft story #2–3 the same way if energy allows, or schedule them into the operating loop (P5.S8).

**VERIFICATION CHECKLIST:**
- [ ] /stories live with story #1; its charts are live embeds citing sources, not images.
- [ ] Every stated number matches its chart (founder-verified); no claim exceeds the data.
- [ ] The story's social card renders; the story appears in analytics as a landing page after sharing.

**IF IT GOES WRONG:** The story drifts toward opinion → cut it back to what the charts show; the portal's neutrality is a long-term asset worth more than a punchy paragraph.

**COMMIT:** `P5.S6: stories section + first data story published`

---

### P5.S7 — The sustainability plan

**GOAL (plain language):** Write down, honestly, how this survives: what it costs now and at 10× traffic, what the founder's realistic ongoing time budget is, what funding/partnership paths exist, and what happens if the founder must step away (the continuity note).

**WHY IT MATTERS:** Blueprint §7 P5: "sustainability plan." Blueprint principle 6 chose boring technology for 10-year durability — this step does the same for money and time. Free public goods die of quiet exhaustion, not technical failure; a written plan is the defense.

**PREREQUISITES:** P5.S6. **Mostly founder thinking; Claude structures and informs.**
**TIME ESTIMATE:** 90–120 minutes.

**ACTIONS:**
1. Instruct Claude Code:
   > "Draft docs/sustainability-plan.md for founder revision: (a) current monthly cost, itemized, and projections at 10× and 100× traffic given our caching architecture; (b) the monthly founder-time budget the P4 automation implies (review queue, alert response, triage, a story) — estimate honestly from the logs; (c) funding options with pros/cons for a neutrality-critical data portal: grants (open-data/civic-tech funders), institutional partnerships (universities, research institutes), donations, sponsorship — and what we would NEVER do (paywall the data, sell user data, undisclosed sponsored content); (d) a continuity note: everything an inheriting maintainer needs is in docs/ + dbt docs + runbooks — name the gaps if any; (e) a 12-month review date."
2. Founder revises — especially (c): which paths you'd actually pursue, and the red lines. The red lines get written into the doc explicitly.
3. Fill any continuity gaps found in (d) (usually a missing runbook), commit the plan.

**VERIFICATION CHECKLIST:**
- [ ] sustainability-plan.md committed: costs (now/10×/100×), time budget, funding paths, explicit red lines, review date.
- [ ] The continuity check names no unfilled gap (or the gap-filling runbooks were written in this step).
- [ ] The founder can state the monthly cost and monthly time commitment from memory — the plan is real, not filed.

**IF IT GOES WRONG:** The honest time budget exceeds what the founder can sustain → shrink scope deliberately in the plan (fewer sources, slower cadence) rather than silently burning out; a smaller living portal beats a large abandoned one.

**COMMIT:** `P5.S7: sustainability plan (costs, time, funding paths, red lines, continuity)`

---

### P5.S8 — Public announcement + the steady-state operating loop

**GOAL (plain language):** Announce the portal publicly, then formally end the build-phase era: adopt a written monthly operating loop (review queue, alert response, triage, one improvement wave, one story) and run its first full month.

**WHY IT MATTERS:** This is where the project changes shape — from "phases with exit criteria" to "a public service with a rhythm." The master prompt marks Phase 5 open-ended: this step IS the open end, made into a routine so it survives ordinary life.

**PREREQUISITES:** P5.S1–S7 all closed.
**TIME ESTIMATE:** 90 minutes for the announcement + loop setup; then the loop's first month (~2–4 hours/month, per the P5.S7 budget).

**ACTIONS:**
1. Instruct Claude Code:
   > "Draft the public announcement (EN + NE) for the founder's channels: what the portal is, what it holds today (sources, indicator count, maps, downloads, API), the privacy stance, and how to request data. Then write docs/runbooks/operating-loop.md — the monthly rhythm: weekly (glance at /status, respond to alerts, review any staged data); monthly (triage feedback/requests into the backlog, ship one improvement wave, publish one story if feasible, check analytics against the sustainability plan's assumptions, dependency updates per §3.8); quarterly (re-run the restore drill, re-run a stranger test, review the sustainability plan). Each item names its exact command or page."
2. Founder announces (own channels; relevant communities where self-promotion is welcome).
3. Run the loop for one full month, logging each weekly/monthly item in PROJECT_LOG as usual.
4. Close the phase: final checklist below; PROJECT_LOG entry closing the build era and opening the operating era.

**VERIFICATION CHECKLIST (= PHASE 5 EXIT CRITERIA):**
- [ ] Public announcement made; a visible visitor bump in analytics.
- [ ] 10+ real external users total; 1+ externally-requested dataset shipped via the queue (from P5.S4–S5).
- [ ] operating-loop.md adopted and its first full month executed, evidenced by PROJECT_LOG entries.
- [ ] Sustainability plan in force; costs and time inside its budget for the first month.
- [ ] All suites green; everything merged and pushed; /requests and /stories are live and current.
- [ ] The founder can say what happens next Monday without opening a step file — the loop, not a phase, now drives the project.

**IF IT GOES WRONG:** The first loop month slips → that's signal, not failure; adjust the loop's cadence in the runbook to what proved sustainable and re-run the month. The loop must be true, or it will be abandoned.

**COMMIT:** `P5.S8: phase 5 closed — portal launched, steady-state operating loop adopted`

---

## After Phase 5

There is no Phase 6 file — by design. The project now runs on `docs/runbooks/operating-loop.md`, the ranked backlog, and the dataset request queue. New large ambitions (a major feature, a big new source class, Devanagari numerals, self-hosting migration) should be written up the same way everything else was: an entry in docs/decisions/ if architectural, then a small step file of their own under `docs/steps/` (e.g. `project-<name>-steps.md`), governed by the same Master Prompt. The method outlives the phases.
