# START HERE — the implementation backlog, in order

**Last updated 2026-07-19 (Fable 5 planning day). This is the single entry
point for any implementing session, any model. One step per session unless a
file says otherwise.**

## How to run any step (the whole protocol)

1. Open Claude Code (or equivalent) in this project folder.
2. Read `CLAUDE.md` (orientation + non-negotiable rules) and the NEWEST entry
   of `docs/PROJECT_LOG.md` (current state).
3. Say exactly: **"We are on step <ID> of docs/steps/<file>. Follow it under
   the master prompt."**
4. The step's VERIFICATION CHECKLIST is the acceptance gate. All three
   verification gates green before any commit: `make lint` · `make test` ·
   `cd web && npm run build`.
5. End every session with a PROJECT_LOG entry (newest at top) and the step's
   COMMIT message. Push to `master` deploys the site + API automatically.
6. Working style (founder's standing preference): execute the whole step
   autonomously, self-verify, present results in plain language. Stop ONLY at
   explicit STOP markers inside a step.

## The order (work top to bottom; ⛔ = do not reorder past this)

| # | Step(s) | File | What it delivers |
|---|---------|------|------------------|
| 1 | P2B.S1 | `phase-2b-expansion-steps.md` | ⛔ Official 2020 map (Limpiyadhura). Recon half DONE — read the in-step update note first |
| 2 | P2B.S2 | `phase-2b-expansion-steps.md` | ⛔ Scheduled ingestion + freshness API (everything later inherits this) |
| 3 | P2B.S3a/b | `phase-2b-expansion-steps.md` | World Bank full catalog (~1,400 indicators). Has a founder STOP between a and b |
| 4 | P2B.S4 | `phase-2b-expansion-steps.md` | Headline-answer policy (one number per question) |
| 5 | P2B.S5a/b + P2B.S6 | spec: `../specs/frontend-sector-portal-spec.md` | ⛔ Sector portal + orbit landing. Follow the SPEC for the how; the steps are acceptance gates. Founder screenshot-approval STOP before deploying the orbit |
| 6 | NGP.S1–S2 | `onboard-nationalgeoportal.md` | Official boundaries + the 753-municipality web map (unblocks #8) |
| 7 | P2B.S7 (families A–E) | `phase-2b-expansion-steps.md` | All census topics at province+district |
| 8 | P2B.S8a/b | `phase-2b-expansion-steps.md` | Municipality-level census + drill-down UI |
| 9 | MOF.S1 then MOF.S4 | `onboard-mof-publications.md` | MoF publications raw mirror + public bilingual library page |
| 10 | WBF.S1–S3 | `onboard-wb-nepal-fiscal.md` | Federal + provincial fiscal series (Tableau spike first — fail-safe) |
| 11 | BUD.S1–S4 | `budget-center.md` | **The Budget Center** (3-tier budget dashboard) — needs #9's mirror + #10's series + #6's municipality map |
| 12 | ODN.S1–S2 | `onboard-opendatanepal.md` | CKAN client + Kalimati daily prices (flagship) |
| 13 | ECN.S1–S4 | `onboard-election-commission.md` | Governance sector: turnout maps + election results |
| 14 | ODN.S3–S5, MOF.S2–S3, P2B.S9–S11, WBF.S4, NGP.S3, ECN follow-ups | respective files | The long tail — any order, founder's pick |

Items 6–13 are largely independent of each other; reorder them freely by the
founder's priorities. Items 1–5 are the foundation — keep their order.

## The explicit STOP points (only places to wait for the founder)

- P2B.S3a→b: founder reviews the WB catalog summary.
- P2B.S6 / frontend spec §8: founder approves orbit screenshots BEFORE deploy.
- P2B.S1: only if no verifiable 2020-boundary source is found.
- WBF.S1 / ECN.S1 / MOF.S3 / ODN basket-size: only if the flagged fallback
  condition triggers.
- BUD.S1: only if projected DB usage exceeds the stated budget.

## Standing rules (apply to every single step — no exceptions)

Raw before parsed · idempotent re-runs · report-never-guess (unknown labels
fail loudly) · staging+review for human-made files (Excel/PDF/uploads) ·
UTF-8 stdout in every script · provenance on every chart · plain language to
the founder · PROJECT_LOG entry every session.
