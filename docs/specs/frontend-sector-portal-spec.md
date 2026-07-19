# Frontend Implementation Spec — Sector Portal + "Nepal Data Orbit" Landing

**Version 1.0 — July 2026. Authored with Fable 5: all design judgment is
pre-made here. The implementing model (Opus, Sol, etc.) should EXECUTE and
VERIFY, not redesign. Where this spec is silent, match the existing codebase's
style; where tempted to "improve" a decision, don't — flag it in the final
report instead.**

This spec is the implementation detail for steps **P2B.S5** and **P2B.S6** in
`docs/steps/phase-2b-expansion-steps.md` (read their checklists too — they are
the acceptance gates). Founder decisions already locked: sector-first portal
(decision 0003), DASHBOARD-style sector pages, orbit landing concept with a
founder go/no-go on screenshots BEFORE deploy.

---

## 0. Context a fresh model needs (read, don't skip)

- **Stack:** Next.js 14 App Router, TypeScript strict, in `web/`. Charts:
  **modular** ECharts via `web/components/EChart.tsx` (`echarts/core` +
  explicitly registered pieces ONLY — never `import * from "echarts"`, never
  `echarts-for-react`; that discipline is why first-load JS is ~92–99 kB).
- **Design system:** `web/app/globals.css` — warm paper `--paper`, white cards,
  navy ink `--ink`, crimson accent `--crimson: #bb2340`, Fraunces (display) +
  Inter (UI) via `next/font`. Reuse existing classes (`.panel`, `.controls`,
  `.segmented`, `.chip`, `.summary-row`, `.state`, `.attribution`,
  `.table-wrap`, `.btn`, `.skeleton`) before writing new CSS.
- **API client:** `web/lib/api.ts` (`fetchIndicators`, `fetchSeries`,
  `fetchGeoValues`, typed). Base URL from `NEXT_PUBLIC_API_BASE` (inlined at
  build). Formatters in `web/lib/format.ts`; CSV in `web/lib/csv.ts`.
- **Existing pages:** `/` (landing: hero + HeroStats tiles + sector cards +
  trust strip), `/explore` (annual indicator explorer), `/banking` (NRB
  monthly dashboard), `/population` (census choropleth). Server `page.tsx`
  wrappers own `metadata`; interactive bodies are client components in
  `web/components/`.
- **Deploy:** push to `master` auto-deploys BOTH Vercel projects (site + API).
  Local verify: `cd web && npm run build` must pass (strict TS); `npx next
  start -p <port>` + `curl` for route smoke.
- **Data now vs later:** ~60 indicators today; the WB full mirror (P2B.S3) will
  grow this to ~1,400 WITHOUT frontend changes — every list in this spec must
  render fine at both scales (virtualization NOT needed; simple filter + group
  is enough at 1,400 rows).
- **House rules:** never invent data or labels; every chart shows provenance;
  error states say what happened and offer the table; all text readable by a
  non-technical founder.

**Indicator universe today (codes you may rely on):**
- WB `economy`: GDP_USD, GDP_GROWTH, GDP_PCAP_USD, CPI_YOY, REMITTANCES_USD,
  REMITTANCES_GDP, EXPORTS_GDP, IMPORTS_GDP, RESERVES_USD, INTERNET_USERS,
  FDI_USD · `population`: POP_TOTAL, POP_GROWTH, URBAN_POP_PCT · `health`:
  LIFE_EXPECTANCY, INFANT_MORTALITY · `education`: ADULT_LITERACY,
  SCHOOL_ENROLL_PRIMARY · `labor`: UNEMPLOYMENT · `environment`:
  ELECTRICITY_ACCESS
- NRB (all topic=economy in DB): 35 codes prefixed `NRB_BFS_` (monthly, with
  `breakdowns.bfi_class`; interest-rate series exist only for
  `commercial_banks`).
- Census (topic=population except literacy=education): CENSUS_POP_TOTAL,
  CENSUS_SEX_RATIO, CENSUS_POP_DENSITY, CENSUS_POP_GROWTH,
  CENSUS_LITERACY_RATE (single year "2021"; POP_TOTAL + LITERACY have
  `breakdowns.sex`).

---

## 1. `web/lib/sectors.ts` — the single source of truth for the portal's shape

Create this file as REVIEWABLE DATA (typed constants + comments), exporting:

```ts
export interface SectorDef {
  slug: string;          // route: /{slug}
  title: string;
  titleShort: string;    // for nav + orbit nodes
  description: string;   // one sentence, founder-tone, no hype
  topics: string[];      // DB topics owned by this sector
  extraCodes?: string[]; // explicit adoptions from other topics
  excludePrefixes?: string[]; // codes carved OUT of this sector
  headlineCodes: string[];    // curated charts, in display order (≤4)
  mapCard?: { href: string; label: string; note: string }; // optional map link card
  orbitCode?: string;    // ONE code whose latest value shows on the orbit node
  external?: { href: string; label: string }; // e.g. full NRB dashboard link
}
```

The eight sectors, EXACTLY (order = nav order = orbit order):

| slug | titleShort | topics | carve rules | headlineCodes | orbitCode |
|---|---|---|---|---|---|
| `economy` | Economy | economy | excludePrefixes: ["NRB_BFS_"] | GDP_GROWTH, CPI_YOY, REMITTANCES_GDP, GDP_PCAP_USD | GDP_GROWTH |
| `finance` | Finance | — | extraCodes: every `NRB_BFS_*` (match by prefix at runtime) | NRB_BFS_LENDING_RATE, NRB_BFS_NPL_RATIO, NRB_BFS_MOBILE_BANKING_USERS | NRB_BFS_LENDING_RATE |
| `people` | People | population | — | POP_TOTAL, POP_GROWTH, URBAN_POP_PCT | CENSUS_POP_TOTAL |
| `health` | Health | health | — | LIFE_EXPECTANCY, INFANT_MORTALITY | LIFE_EXPECTANCY |
| `education` | Education | education | — | ADULT_LITERACY, SCHOOL_ENROLL_PRIMARY | ADULT_LITERACY |
| `labor` | Labor | labor | — | UNEMPLOYMENT | UNEMPLOYMENT |
| `environment` | Environment | environment, agriculture | — | ELECTRICITY_ACCESS | ELECTRICITY_ACCESS |
| `governance` | Governance | governance | — | (none yet) | (none — node shows "in preparation") |

Extras: `people.mapCard = { href: "/population", label: "Census 2021 on the
map", note: "Population, density, literacy for every province and district" }`;
`finance.external = { href: "/banking", label: "Open the full banking
dashboard" }`; `education.mapCard = { href: "/population", label: "Literacy on
the map", note: "Census 2021 literacy by district" }`.

Titles/descriptions (use verbatim):
- Economy — "Economy" / "Growth, prices, trade, remittances, and investment —
  Nepal's macro picture across six decades."
- Finance — "Finance & Banking" / "Nepal's banking system month by month, from
  Nepal Rastra Bank's statistics."
- People — "People & Population" / "Who lives in Nepal, where, and how that is
  changing — census counts and demographic series."
- Health — "Health" / "Life expectancy, child survival, and the health of
  Nepal's people over time."
- Education — "Education" / "Literacy and schooling — how Nepal learns, from
  census counts and international series."
- Labor — "Labor" / "Work and employment in Nepal."
- Environment — "Agriculture & Environment" / "Land, energy, and environment."
- Governance — "Governance" / "Public institutions and governance indicators."

Membership function (export `indicatorsForSector(defs, indicators)`): an
indicator belongs to a sector if `sector.topics.includes(ind.topic)` and no
excludePrefix matches, OR any extraCodes/prefix rule matches. Every indicator
must land in EXACTLY ONE sector — add a dev-only console.warn for orphans or
double-assignments (this guards the P2B.S3 backfill).

**Source badge rule (until P2B.S4 formalizes):** code starts `NRB_BFS_` →
"Nepal Rastra Bank"; starts `CENSUS_` → "National Statistics Office"; else
"World Bank". Export `sourceForCode(code)`.

## 2. Navigation

`web/components/SiteHeader.tsx`: nav becomes **Overview · Data ▾ · Population
map · Banking**. "Data ▾" is a dropdown listing the 8 sectors (titleShort +
tiny count once loaded is NOT needed — keep it static, no fetch in the
header). Implementation: `<details className="nav-dd">` with `<summary>Data</summary>`
and a `<ul>` panel — native disclosure = keyboard/SR accessible for free; add
CSS to close on outside click via `onBlur` is NOT needed (native toggle is
acceptable). Active state: keep `aria-current` logic; a sector route marks
"Data" active. Mobile (<560px): the dropdown panel becomes full-width below
the bar. CSS: panel = white card, hairline border, `--shadow-2`, 8 rows,
hover wash; z-index above sticky header.

## 3. Sector pages — `web/app/[sector]/page.tsx` (dashboard style)

**Routing:** one dynamic segment with `generateStaticParams()` returning the 8
slugs and `export const dynamicParams = false` (unknown slugs 404). Server
component: builds `metadata` from the SectorDef (title = sector title,
description = sector description) and renders
`<SectorDashboard slug={...} />` (client). NOTE: existing static routes
(`/explore`, `/banking`, `/population`) take precedence over `[sector]` — no
collision, but VERIFY all four still render after adding the dynamic route.

**`web/components/SectorDashboard.tsx` layout, top to bottom:**
1. `.page-head` — crumb "Overview / {title}", h1 title, `.sub` description,
   plus a meta line: "{N} indicators · sources: {distinct badge names}"
   (computed after fetch).
2. **Headline band** — CSS grid `repeat(auto-fit, minmax(300px, 1fr))`, each
   cell a `.panel` containing a `<HeadlineChart code={...} />`; if the sector
   has a `mapCard`, it renders as one more cell: crimson-accent card with
   label, note, and "Open the map →" (reuse `.sector-card` styling). If
   `external` exists, render a `.btn ghost small` link beside the band title.
   Band title: `<h2>` "At a glance".
3. **Full list** — `<h2>` "All {title} indicators". A `.controls` row with ONE
   text input (`.field` styled like selects; placeholder "Filter indicators…")
   filtering client-side on name+code (case-insensitive substring). Below, the
   list grouped by source badge (World Bank / NRB / NSO groups, in that
   order), each row: indicator name (link) · years-covered NOT available from
   /v1/indicators — show unit chip instead · source badge. Row link:
   `/explore?indicator={code}` for annual codes; `NRB_BFS_*` rows link to
   `/banking` (the dashboard preselects via query param — see §4). Rows are
   plain `<a>` list items with hairline separators and hover wash (add
   `.ind-row` CSS: flex, 10px 12px padding, name in `--ink` 0.95rem, badge
   right-aligned).
4. **Governance empty state:** if the sector has 0 indicators, render `.state`
   with: "No governance indicators are loaded yet. They arrive with the full
   World Bank catalog (step P2B.S3)." — honest, no fake cards.
5. Footer attribution: ".attribution" line naming the sector's sources.

**`web/components/HeadlineChart.tsx`** (client): props `{ code: string }`.
- Fetches `fetchSeries(code, "NP")`; loading = `.skeleton` block 220px tall;
  error = compact `.state error` (not full-height — override min-height 160px).
- **Breakdown filtering (IMPORTANT):** if any observation has
  `breakdowns.bfi_class`, keep only `overall` if present else
  `commercial_banks`; if any has `breakdowns.sex`, keep only rows with empty
  breakdowns. Pass the FILTERED copy of the DataResponse to the chart.
- Renders: `.k`-style label (indicator name, linked to explore/banking as in
  §3.3), big latest value + period (reuse `.summary-row .v` styling), then a
  **small** TrendChart variant: add an optional `height` prop to
  `web/components/TrendChart.tsx` (default 420; headline uses 200) and an
  optional `compact` prop that hides the y-axis name and shrinks grid padding.
  Single series stays crimson. No legend.
- Source line: 0.75rem muted "{source badge} · {latest period}".

## 4. Deep links into the existing dashboards

- `/explore`: read `?indicator=CODE`. Next 14 gotcha: `useSearchParams()`
  requires a `<Suspense>` boundary in the page — wrap `<ExploreDashboard />`
  in `<Suspense fallback={null}>` in `web/app/explore/page.tsx`, then inside
  the client component initialize selection from the param once indicators
  load (validate the code exists in the list; ignore invalid). The existing
  default (GDP_GROWTH) applies when absent.
- `/banking`: same pattern with `?indicator=NRB_BFS_...` (validate against its
  NRB list; keep NPL default).
- Verify `npm run build` still marks both routes static (`○`) — with Suspense
  it does; if a route flips to dynamic (`λ`), you've read params in the server
  page — move it back into the client component.

## 5. Landing page — replace sector cards; add the ORBIT hero (P2B.S6)

**Keep:** eyebrow, h1, lede, CTA row, HeroStats tiles, trust strip, footer.
**Replace:** the static ridgeline SVG + the 3 sector cards section.

**`web/components/DataOrbit.tsx`** — the hero visual. Concept: center = Nepal
silhouette; the 8 sectors orbit it as nodes; each node shows titleShort + one
live number; click navigates to the sector.

Geometry & implementation (do it EXACTLY like this):
- Container: `position:relative`, square, `min(92vw, 560px)`, placed to the
  right of the hero text at ≥900px (CSS grid `1.1fr 1fr`), below it centered
  at <900px, and at <560px the orbit is REPLACED by a static 2×4 grid of the
  same nodes (no animation, no absolute positioning — reuse node markup).
- Center: inline SVG of Nepal. Generate the path ONCE at authoring time:
  `npx -y mapshaper web/public/maps/nepal-provinces.json -dissolve2 -simplify
  20% keep-shapes -o format=svg nepal-outline.svg`, open the output, copy the
  single `<path d="...">` and its viewBox into the component (fill
  `--crimson` at 90% opacity, no stroke). If the path exceeds ~6 kB, rerun
  with `-simplify 10%`. Under it, centered text: "नेपाल" (Fraunces, 1.1rem,
  ink) and "Nepal in data" (0.8rem, muted).
- Orbit ring: one absolutely-positioned div `.orbit-ring` (border: 1px dashed
  `--hairline-2`, border-radius 50%, inset 6%) purely decorative,
  `aria-hidden`.
- Nodes: 8 `.orbit-node` anchors absolutely positioned by angle
  `θ_i = -90° + i·45°` on an ellipse `rx = 46%`, `ry = 42%` of the container
  (slight vertical squash reads better): `left = 50% + rx·cos θ`,
  `top = 50% + ry·sin θ`, `transform: translate(-50%, -50%)`. Compute the 8
  positions as literal percentages in the code (comment the formula) — no
  runtime trig needed.
- **Animation (CSS only):** the node CONTAINER `.orbit-rotor` spins
  `rotate(360deg)` over **150s linear infinite**; each node counter-rotates
  (`animation: counterspin 150s linear infinite reverse`) so text stays
  upright. This is the classic rotor/counter-rotor pattern — nodes drift
  serenely, nothing "spins". Hover on the container pauses both
  (`animation-play-state: paused`). `@media (prefers-reduced-motion: reduce)`:
  no animation at all.
- Node contents: titleShort (600 weight, 0.85rem) + value line (Fraunces,
  1.05rem) — live number for its `orbitCode` (fetch pattern: ONE
  `Promise.allSettled` over the 7 orbitCodes reusing the HeroStats
  latest-with-breakdown-preference helper — EXTRACT that helper into
  `web/lib/latest.ts` and import it in both places, don't duplicate). While
  loading: `.skeleton` chip. Governance node: value line "in preparation",
  muted. Node style: white card, hairline border, radius 999px (pill), padding
  8px 16px, `--shadow-1`, hover lifts (`--shadow-2`, translateY(-2px)) and
  border-color ink; focus-visible ring per the design system.
- **Accessibility (non-negotiable):** the orbit is `aria-hidden="true"` as a
  VISUAL; immediately after it in the DOM render a visually-hidden (`.sr-only`
  — add the utility class) `<nav aria-label="Sectors">` plain list of the 8
  sector links. Keyboard users tab through REAL links — the visible nodes are
  the same anchors (they're focusable and clickable); the sr-only nav is a
  fallback for screen-reader table-of-contents navigation. Verify tab order
  hits all 8.
- **Budget:** zero new dependencies. The component adds only its own code +
  the inlined path — well under the 40 kB JS budget. Confirm in the build
  output that `/` first-load stays ≤ 110 kB.

**Hero copy update:** h1 stays "Nepal's numbers, in one trustworthy place.";
lede unchanged; CTA row: primary "Explore the data" → keep pointing at
`/explore`; ghost becomes "Browse sectors" → scrolls to the sector list
section (`href="#sectors"`).

**Below the fold:** replace the old 3-card sector grid with an `id="sectors"`
section titled "Browse by sector" rendering all 8 sectors as `.sector-card`s
(icon optional — reuse the 3 existing SVG icons for economy/finance/people and
add five minimal 24×24 line icons in the same 1.8-stroke style: heart-pulse
(health), open book (education), briefcase (labor), leaf (environment),
building-columns (governance); keep each under 10 lines of SVG). Card meta
line: "{N} indicators" once loaded (fetch once, pass counts down; skeleton
while loading).

## 6. CSS additions (globals.css) — keep the token discipline

New classes only (reuse everything else): `.nav-dd` (+ panel), `.ind-row`,
`.headline-grid`, `.orbit-wrap`, `.orbit-ring`, `.orbit-rotor`, `.orbit-node`,
`.sr-only`, `@keyframes orbit-spin` / `orbit-counterspin`, and the hero grid
change (`.hero` becomes the 2-col grid at ≥900px). Nothing hardcodes colors —
tokens only. Dark mode remains out of scope (light-only site).

## 7. Playwright smoke + screenshots (this is also the founder-approval tool)

1. `cd web && npm i -D @playwright/test && npx playwright install chromium`.
2. `web/playwright.config.ts`: testDir `e2e`, baseURL `http://localhost:3199`,
   `webServer: { command: "npx next start -p 3199", reuseExistingServer: true }`
   (build first in CI).
3. `web/e2e/smoke.spec.ts`:
   - `/` renders: h1 text present; ≥7 orbit/sector links visible; HeroStats
     shows a real number within 15s (regex `\d`), OR skeletons remain and the
     test only warns (API may be cold) — do not hard-fail on live-data timing.
   - `/economy` renders: "At a glance" heading + at least one canvas with
     nonzero size; list shows ≥5 `.ind-row`s.
   - `/population` renders: map canvas present within 20s.
   - `/explore?indicator=CPI_YOY` shows "Inflation" in the chart title.
   - Screenshot suite: `/` and `/economy` at 360×780, 768×1024, 1440×900 →
     save to `../Screenshots/preview-{page}-{width}.png` (the repo's
     Screenshots/ folder — the founder reviews files there).
4. CI: add a `web-e2e` job to `.github/workflows/ci.yml`: build, install
   chromium (`npx playwright install --with-deps chromium`), run tests with
   `NEXT_PUBLIC_API_BASE=https://nepal-data-base-project.vercel.app`. Cache
   `~/.cache/ms-playwright` keyed on the playwright version.

## 8. Verification gates & the STOP

In order: `cd web && npm run build` (all routes static; budgets: every route
≤ 120 kB first-load, `/` ≤ 110 kB — report the table) → Playwright suite green
locally → **STOP: show the founder the Screenshots/preview-*.png files and the
local URL (`npx next start`, tell them the localhost address to open) and get
an explicit GO** → only then commit + push (auto-deploys) → after deploy,
curl-verify `/`, one sector page, `/explore?indicator=CPI_YOY` on the live
domain → PROJECT_LOG entry (house format: what/evidence/next) → done-report to
the founder in plain language.

If the founder says the orbit looks gimmicky: fallback = keep the new sector
cards + nav + sector pages (deploy those), restore the ridgeline hero, park
`DataOrbit.tsx` behind an unused flag, and note it in the log. The sector
portal ships regardless — the orbit is the only reversible piece.

**Commits (2):**
`P2B.S5: sector portal — 8 dashboard-style sector pages, nav, deep links`
`P2B.S6: landing "Nepal data orbit" hero (a11y fallback, CSS-only motion)`

## 9. Known traps (each cost a real debug once — don't rediscover)

1. Importing anything from a chart component into a dashboard EAGERLY drags
   ECharts into that route's first load — shared constants live in `web/lib/`
   (see `bankingPalette.ts` precedent).
2. `useSearchParams` without `<Suspense>` fails `next build`.
3. `formatValue`/`formatAxis` handle PCT/USD/COUNT — PERSONS falls through to
   plain formatting; that's fine, don't "fix" it.
4. NRB interest-rate series have ONLY `commercial_banks` breakdowns — a filter
   that insists on `overall` will render an empty chart.
5. The API sleeps never, but a cold serverless hit can take 2–4s — loading
   states must look intentional (skeletons, not spinners).
6. Windows dev shell: don't pipe emoji/Devanagari through cmd tools in npm
   scripts (cp1252) — files are fine, console output isn't.
7. `next/font` downloads at build — CI needs network (it has it); never switch
   to CDN links (CSP + perf).
