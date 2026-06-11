# PHASE 0 — FOUNDATIONS — Step File

**Version 1.0 — June 2026**
**Governed by: Master Prompt v1.0 · Architecture Blueprint v1.0**
**Phase goal: every account, tool, and document needed to build is in place and secured. No code is written in this phase — we are preparing the workshop before touching the wood.**
**Total founder time: roughly 2–3 hours, can be split across days.**
**Phase exit criterion: the checklist in P0.S5 passes completely.**

---

### P0.S1 — Create and secure your GitHub account

**GOAL (plain language):** Get the online vault where every line of the project's code will live, with its full history, protected by two-step login.

**WHY IT MATTERS:** Git/GitHub is the project's permanent memory and undo button (Master Prompt, Prime Directive 3). If your laptop dies, the project survives. Two-factor authentication (2FA) matters because this account will eventually control a public website — it must not be hijackable with just a password.

**PREREQUISITES:** An email address you control long-term and a smartphone.

**TIME ESTIMATE:** 20–30 minutes.

**ACTIONS:**
1. Go to https://github.com and click Sign up. Choose a username you're happy seeing publicly for years (it can be personal, e.g. `yourname`, or project-flavored, e.g. `nepaldataproject`). Use a strong, unique password — ideally from a password manager.
2. Verify your email when GitHub sends the confirmation link.
3. Turn on 2FA: click your profile photo (top right) → Settings → Password and authentication → Two-factor authentication → Enable. Choose "Authenticator app" and scan the QR code with a free authenticator app on your phone (Google Authenticator, Microsoft Authenticator, or similar).
4. GitHub will show you **recovery codes**. Save these somewhere safe that is NOT your phone (write them on paper or store in a password manager). If you lose your phone, these codes are the only way back in.
5. That's it. Do not create any repository yet — that happens in P0.S4, done properly with the full skeleton.

**VERIFICATION CHECKLIST:**
- [ ] You can log out of GitHub and log back in, and it asks for an authenticator code.
- [ ] Your recovery codes are saved somewhere that is not your phone.
- [ ] You can visit `https://github.com/YOUR-USERNAME` and see your (empty) profile page.

**IF IT GOES WRONG:**
- Didn't receive the verification email → check spam, or Settings → Emails → resend.
- Authenticator app confusion → GitHub's own guide is good: search "GitHub configure two-factor authentication" or ask Claude in a chat, describing exactly what's on your screen.

**COMMIT:** None — no code exists yet.

---

### P0.S2 — Create your Supabase account and database project

**GOAL (plain language):** Set up the managed home for our PostgreSQL database and raw-file storage — the "warehouse building" the data will live in — without you ever administering a server.

**WHY IT MATTERS:** The blueprint (§6) chose Supabase because it gives us professional PostgreSQL plus file storage plus automatic backups on a free tier, and because it's plain PostgreSQL underneath, we can move out anytime with no redesign. This is the standard "managed first, self-host later if ever needed" play.

**PREREQUISITES:** P0.S1 done (we'll sign in with GitHub — one less password to manage).

**TIME ESTIMATE:** 15–20 minutes.

**ACTIONS:**
1. Go to https://supabase.com and choose Sign in with GitHub. Authorize it.
2. Create a new organization if prompted (name it e.g. `nepal-data-portal`), on the Free plan.
3. Create a new project:
   - Name: `nepal-data-portal-dev` (this is our development database; a separate production one comes in Phase 3).
   - Database password: have Supabase generate a strong one, and store it in your password manager immediately. **This password is a secret — never paste it into any chat, file, or email.** Claude will only ever ask you to put it into a local `.env` file that stays on your machine.
   - Region: choose Singapore (closest reliable region to Nepal — lower latency).
4. Wait the minute or two while the project provisions.
5. Look around but change nothing: open the Table Editor (left sidebar) — it will be empty. Empty is correct. Tables will be created only through migrations (Master Prompt §3.2), starting in Phase 1.

**VERIFICATION CHECKLIST:**
- [ ] Supabase dashboard shows project `nepal-data-portal-dev` with a green/active status.
- [ ] The database password is stored in your password manager.
- [ ] Table Editor opens and shows no tables.

**IF IT GOES WRONG:**
- Region not available on free tier → pick the nearest available Asian region; note which one in PROJECT_LOG later.
- Forgot the database password → Supabase project settings allow a database password reset; do it and store it properly this time.

**COMMIT:** None — no code exists yet.

---

### P0.S3 — Install Claude with Claude Code (your build tool)

**GOAL (plain language):** Put the tool on your computer that lets Claude actually create files, run programs, and build the project on your machine while you watch and approve.

**WHY IT MATTERS:** Chat can design; Claude Code can *build*. Every hands-on step from Phase 1 onward assumes it. Without it, you'd be copy-pasting code by hand — slow and error-prone.

**PREREQUISITES:** A computer (Windows, Mac, or Linux) where you're allowed to install software. **A paid Claude plan (Pro or above) — Claude Code is not included in the free plan.** If you're on the free plan, this is the moment the project needs its first small budget; Pro is the entry option.

**TIME ESTIMATE:** 20–40 minutes.

**ACTIONS:**
1. Recommended route for you — the Desktop app (no terminal needed): download the Claude Desktop app from https://claude.ai/download and install it. The Desktop app includes Claude Code with a graphical interface, so you can skip the command line entirely.
2. Sign in with your Claude account.
3. Open the Claude Code area of the app and let it finish any first-run setup it asks for.
4. Optional, later: the terminal version of Claude Code exists too (official guide: https://code.claude.com/docs/en/setup). Ignore it for now — the Desktop route is enough, and we can always add it.
5. Create a home for the project on your computer: make a folder called `projects` in your home/user directory. (You can do this in your file manager — no terminal needed.)
6. **First contact test:** In Claude Code, open/point it at the `projects` folder and give it this exact instruction:
   > "Create a folder called `hello-test` containing a file `hello.txt` with the text 'Namaste, Nepal Data Portal'. Then tell me exactly where it is on disk."
7. Find that file yourself in your file manager and open it. Seeing it with your own eyes — not just trusting the chat — is the habit this whole project runs on.
8. Delete the `hello-test` folder afterward; it was only a handshake.

**VERIFICATION CHECKLIST:**
- [ ] Claude Desktop app opens and you are signed in on a plan that includes Claude Code.
- [ ] The hello-test instruction worked, and you personally found and opened `hello.txt` in your file manager.
- [ ] You know where your `projects` folder is.

**IF IT GOES WRONG:**
- Claude Code not available in your app/plan → check your plan level; the official requirements live at https://code.claude.com/docs/en/setup.
- Anything else → open a normal Claude chat, paste the exact error or describe the screen, and troubleshoot live. Installation problems are common and always solvable.

**COMMIT:** None — the test folder is deliberately disposable.

---

### P0.S4 — Create the repository with the full project skeleton

**GOAL (plain language):** Create the project's official folder structure on your computer and its mirrored vault on GitHub, with the founding documents inside, and make the first commit.

**WHY IT MATTERS:** The skeleton (Master Prompt §3.1) is the filing system every future step assumes. Committing the blueprint and master prompt into the repo means the project's "constitution" is versioned alongside its code forever — exactly how serious teams work.

**PREREQUISITES:** P0.S1 (GitHub), P0.S3 (Claude Code working). Have these three files from your chats with Claude saved somewhere findable: `nepal-data-portal-blueprint.md`, `nepal-data-portal-master-prompt.md`, and this file (`phase-0-steps.md`).

**TIME ESTIMATE:** 30–45 minutes.

**ACTIONS:**
1. Put the three documents into a folder Claude Code can see (e.g. inside your `projects` folder).
2. In Claude Code, pointed at your `projects` folder, give this instruction (paste it whole):
   > "Create a new project folder `nepal-data-portal` with exactly this structure: `docs/` (with subfolders `steps/`, `decisions/`, `runbooks/`), `ingestion/` (with empty subfolders `worldbank/`, `imf/`, `ilo/`, `nrb/`, `nso/`, `ministries/`), `transform/`, `db/migrations/`, `db/seeds/`, `api/`, `web/`, `reference/`, `scripts/`, `tests/`. Move the three markdown documents I've provided into `docs/`, putting `phase-0-steps.md` into `docs/steps/`. Create: a `README.md` that briefly describes the Nepal Data Portal project and points to `docs/` for the blueprint and master prompt; an empty-template `docs/PROJECT_LOG.md` with a heading and a table of Date / Step / What was done / Evidence / Next; a `.gitignore` suitable for Python + Node that also ignores `.env` and any file containing secrets; and a `.env.example` containing the placeholder line `DATABASE_URL=postgres://...` with a comment that real values never go in git. Add a `.gitkeep` file inside every empty folder so the structure is preserved in git. Then initialize a git repository, make the first commit with the message 'P0.S4: repository skeleton and founding documents', create a PRIVATE GitHub repository named nepal-data-portal under my account, and push to it. Walk me through any GitHub authorization it asks for, one screen at a time."
3. Approve the actions Claude Code proposes as it works; ask it to explain anything before approving if unsure. It may need you to authorize GitHub access once — follow its on-screen guidance.
4. When it reports success, verify with your own eyes (checklist below). Trust, but verify — every step, forever.

**VERIFICATION CHECKLIST:**
- [ ] On github.com you see a **private** repository `nepal-data-portal` under your account.
- [ ] Inside it on the website: `docs/nepal-data-portal-blueprint.md` and `docs/nepal-data-portal-master-prompt.md` open and read correctly; `docs/steps/phase-0-steps.md` exists; `docs/PROJECT_LOG.md` exists.
- [ ] The folder structure matches §3.1 of the master prompt (spot-check: `db/migrations/` and `ingestion/nrb/` exist).
- [ ] The repository shows exactly 1 commit, message starting `P0.S4:`.
- [ ] `.env.example` is in the repo; no file with real passwords is.

**IF IT GOES WRONG:**
- GitHub authorization fails → tell Claude Code the exact error; the common fix is signing in via the browser window it opens.
- Repo accidentally created public → on GitHub: repo Settings → General → Danger Zone → change visibility to private. No harm done at this stage.
- Structure came out wrong → instruct Claude Code: "Compare the repository structure against Master Prompt §3.1 in docs/, fix all differences, and commit as 'P0.S4: fix skeleton structure'."

**COMMIT:** `P0.S4: repository skeleton and founding documents`

---

### P0.S5 — Set up the Claude Project and close the phase

**GOAL (plain language):** Make every future chat automatically start with full project knowledge, write the first project-log entry, and formally declare Phase 0 complete.

**WHY IT MATTERS:** Master Prompt §6 (Session Protocol) depends on context being loaded every session. The Claude Project is how that happens without you re-uploading files each time. The log entry starts the habit that keeps a slow-paced project resumable after any gap.

**PREREQUISITES:** P0.S1–P0.S4 all verified.

**TIME ESTIMATE:** 15–20 minutes.

**ACTIONS:**
1. In Claude (app or claude.ai), create a new **Project** named `Nepal Data Portal`.
2. Add to its project knowledge: the blueprint, the master prompt, and this step file.
3. Set the project's custom instructions to exactly:
   > "You are operating under docs/nepal-data-portal-master-prompt.md, governed by docs/nepal-data-portal-blueprint.md. At the start of every conversation: state the last completed step per PROJECT_LOG.md (ask me to paste the latest log if you don't have it), state the current step, and follow the Session Protocol in the master prompt. The founder is non-technical: plain-language previews before actions, verification evidence after."
4. In Claude Code, instruct:
   > "Append a row to docs/PROJECT_LOG.md: today's date | P0.S1–P0.S5 | Phase 0 complete: GitHub secured with 2FA, Supabase project nepal-data-portal-dev created (region noted), Claude Code installed and tested, repository created and pushed, Claude Project configured | Evidence: repo at github.com/USERNAME/nepal-data-portal with 1+ commits | Next: P1.S1, await phase-1 step file. Commit as 'P0.S5: phase 0 closed'."
5. Start a fresh conversation inside the Claude Project and say only: "Status check." It should correctly identify Phase 0 as complete and Phase 1 as next. That proves the memory system works.

**VERIFICATION CHECKLIST (= PHASE 0 EXIT CRITERIA):**
- [ ] GitHub account with 2FA; recovery codes stored safely.
- [ ] Supabase project `nepal-data-portal-dev` active; password in password manager only.
- [ ] Claude Code performs file operations you can verify on disk.
- [ ] Private repo `nepal-data-portal` on GitHub matching the §3.1 skeleton, founding docs inside, ≥2 commits.
- [ ] Claude Project answers "Status check" correctly in a brand-new conversation.
- [ ] PROJECT_LOG.md has its first entry, committed.

**IF IT GOES WRONG:** Nothing here is destructive — redo any sub-action. If the status check answers poorly, re-check that all three documents are actually in the project knowledge.

**COMMIT:** `P0.S5: phase 0 closed`

---

## After Phase 0

Return to Claude and say: **"Phase 0 exit criteria met — generate the Phase 1 step file."** Phase 1 (the walking skeleton) will be written against the master prompt the same way, taking into account anything Phase 0 taught us (note any surprises in PROJECT_LOG — they shape the next file).
