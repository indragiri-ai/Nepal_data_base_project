// The portal's shape as reviewable data (P2B.S5 / decision 0003 — sectors
// organize the site; sources are provenance labels). Every indicator lands in
// EXACTLY ONE sector via `indicatorsForSector`. Edit this file to re-shape the
// portal — the nav, sector pages, and orbit all read from it.

import type { IndicatorSummary } from "@/lib/api";

export interface SectorDef {
  slug: string; // route: /{slug}
  title: string;
  titleShort: string; // nav + orbit nodes
  description: string; // one sentence, founder-tone, no hype
  topics: string[]; // DB topics owned by this sector
  extraCodes?: string[]; // explicit adoptions from other topics
  includePrefixes?: string[]; // adopt every code with this prefix (e.g. NRB_BFS_)
  excludePrefixes?: string[]; // codes carved OUT of this sector
  headlineCodes: string[]; // curated charts, in display order (<=4)
  themes?: ThemeDef[]; // sub-shelves within the sector (see below)
  mapCard?: { href: string; label: string; note: string };
  orbitCode?: string; // ONE code whose latest value shows on the orbit node
  orbitLabel?: string; // the metric name for that value (e.g. "GDP growth")
  /** Shown on the orbit node when no single number can represent the sector —
   *  25 vegetables have 25 prices. Without it the node reads "in preparation",
   *  which would be false for a sector holding 153,494 figures. */
  orbitNote?: string;
  external?: { href: string; label: string };
}

/** A shelf inside a sector.
 *
 *  Economy holds ~676 indicators. Grouped only by source, that is one wall of
 *  cards you can only search if you already know the name of the thing you
 *  want — which defeats browsing. Themes cut the wall into shelves a person can
 *  scan.
 *
 *  `match` is a list of lowercase terms tested at word starts against the
 *  indicator's NAME, first theme wins, and anything unmatched falls to a
 *  visible "Other" group rather than being hidden. This is OUR navigation aid
 *  and nothing more:
 *  it deliberately does not claim to reproduce the World Bank's own taxonomy,
 *  which the warehouse does not store per indicator. Keeping the rule here as
 *  data means a human can read it, argue with it and fix it in one place —
 *  the same reason the sector definitions live in this file.
 */
export interface ThemeDef {
  label: string;
  match: string[];
}

// Order matters: first match wins, so the specific shelves come before the
// broad one. "Growth & national accounts" is LAST for that reason — half the
// catalogue is expressed as a share of GDP, and if it ran first it would
// swallow trade, credit and remittances alike on the strength of their
// denominator. (It did, on first render: 106 indicators, most of them not
// national accounts at all.)
export const ECONOMY_THEMES: ThemeDef[] = [
  // No "cpi" here: it is a prefix of CPIA, the World Bank's policy RATINGS, and
  // it earned nothing anyway — "price" already catches both the consumer price
  // index and inflation.
  { label: "Prices & inflation", match: ["price", "inflation", "deflator"] },
  {
    label: "Government finance",
    match: [
      "tax", "government", "fiscal", "public", "debt", "revenue", "expense",
      "grant", "budget", "subsidies", "military expenditure", "federal",
      "provincial",
    ],
  },
  {
    label: "Trade",
    match: [
      "export", "import", "trade", "tariff", "merchandise", "customs",
      "binding coverage", "bound rate",
    ],
  },
  {
    label: "External & remittances",
    match: [
      "remittance",
      "foreign direct investment",
      "current account",
      "reserve",
      "exchange rate",
      "external",
      "official development",
      "net official",
      "balance of payments",
      "oda",
      "aid",
      "portfolio",
      "charges for the use of intellectual property",
      "net capital account",
      "net errors and omissions",
      "net financial account",
      "net financial flows",
      "net foreign assets",
      "net primary income",
      "primary income",
      "net secondary income",
      "secondary income",
      "personal transfers",
    ],
  },
  {
    label: "Money, credit & interest",
    match: [
      "money", "credit", "interest", "lending", "deposit", "monetary",
      "bank", "financial sector", "automated teller machine", "claims on",
    ],
  },
  {
    label: "Poverty & inequality",
    match: [
      "poverty", "gini", "income share", "inequality", "consumption per capita",
      "below 50 percent of median income", "living in slums",
    ],
  },
  {
    label: "Business & investment",
    match: [
      "business", "firms", "investment", "enterprise", "startup", "industry",
      "manufacturing", "services", "value chain", "b-ready", "bribery",
      "management practices", "operating license",
    ],
  },
  {
    label: "Tourism & transport",
    match: ["air transport", "international tourism", "logistics performance"],
  },
  {
    label: "Digital connectivity",
    match: [
      "broadband", "telephone subscription", "individuals using the internet",
      "mobile cellular", "secure internet server",
    ],
  },
  {
    label: "Research & innovation",
    match: [
      "research and development", "researchers in r&d", "technicians in r&d",
      "patent application", "industrial design application",
      "scientific and technical journal",
    ],
  },
  {
    label: "Policy & institutions",
    match: ["cpia", "ida resource allocation index", "statistical performance indicator"],
  },
  {
    label: "Growth & national accounts",
    match: [
      "gdp", "gross domestic", "gross national", "value added", "gross capital",
      "gross fixed capital", "gross savings", "final consumption", "national income",
      "gni", "adjusted net savings", "adjusted savings", "changes in inventories",
    ],
  },
];

// Order = nav order = orbit order. Titles/descriptions are verbatim per spec.
export const SECTORS: SectorDef[] = [
  {
    slug: "economy",
    title: "Economy",
    titleShort: "Economy",
    description:
      "Growth, prices, trade, remittances, and investment — Nepal's macro picture across six decades.",
    topics: ["economy"],
    excludePrefixes: ["NRB_BFS_"], // banking lives in Finance
    headlineCodes: ["GDP_GROWTH", "CPI_YOY", "REMITTANCES_GDP", "GDP_PCAP_USD"],
    themes: ECONOMY_THEMES,
    orbitCode: "GDP_GROWTH",
    orbitLabel: "GDP growth",
  },
  {
    slug: "food-prices",
    title: "Food Prices",
    titleShort: "Food",
    description:
      "What food costs at Kalimati — daily wholesale prices for 25 everyday vegetables, from the market that sets Nepal's produce prices.",
    topics: [],
    // Matched at runtime, the way Finance adopts the NRB series.
    includePrefixes: ["KALIMATI_"],
    // No curated headline charts: the market-prices panel IS this page.
    headlineCodes: [],
    orbitNote: "daily prices",
  },
  {
    slug: "finance",
    title: "Finance & Banking",
    titleShort: "Finance",
    description:
      "Nepal's banking system month by month, from Nepal Rastra Bank's statistics.",
    topics: [],
    includePrefixes: ["NRB_BFS_"], // every NRB banking series, matched at runtime
    headlineCodes: [
      "NRB_BFS_LENDING_RATE",
      "NRB_BFS_NPL_RATIO",
      "NRB_BFS_MOBILE_BANKING_USERS",
    ],
    orbitCode: "NRB_BFS_LENDING_RATE",
    orbitLabel: "Avg lending rate",
    external: { href: "/banking", label: "Open the full banking dashboard" },
  },
  {
    slug: "people",
    title: "People & Population",
    titleShort: "People",
    description:
      "Who lives in Nepal, where, and how that is changing — census counts and demographic series.",
    topics: ["population"],
    // Census is the headline for population facts (decision 0005); the World Bank
    // POP_TOTAL/POP_GROWTH series appear in the list below, badged as alternatives.
    headlineCodes: ["CENSUS_POP_TOTAL", "CENSUS_POP_GROWTH", "URBAN_POP_PCT"],
    orbitCode: "CENSUS_POP_TOTAL",
    orbitLabel: "Population (2021)",
    mapCard: {
      href: "/population",
      label: "Census 2021 on the map",
      note: "Population, density, literacy for every province and district",
    },
  },
  {
    slug: "health",
    title: "Health",
    titleShort: "Health",
    description:
      "Life expectancy, child survival, and the health of Nepal's people over time.",
    topics: ["health"],
    headlineCodes: ["LIFE_EXPECTANCY", "INFANT_MORTALITY"],
    orbitCode: "LIFE_EXPECTANCY",
    orbitLabel: "Life expectancy",
  },
  {
    slug: "education",
    title: "Education",
    titleShort: "Education",
    description:
      "Literacy and schooling — how Nepal learns, from census counts and international series.",
    topics: ["education"],
    // Census literacy is the headline (decision 0005); the World Bank ADULT_LITERACY
    // series (a different age base, 15+) is listed below as an alternative.
    headlineCodes: ["CENSUS_LITERACY_RATE", "SCHOOL_ENROLL_PRIMARY"],
    orbitCode: "ADULT_LITERACY",
    orbitLabel: "Adult literacy",
    mapCard: {
      href: "/population",
      label: "Literacy on the map",
      note: "Census 2021 literacy by district",
    },
  },
  {
    slug: "labor",
    title: "Labor",
    titleShort: "Labor",
    description: "Work and employment in Nepal.",
    topics: ["labor"],
    headlineCodes: ["UNEMPLOYMENT"],
    orbitCode: "UNEMPLOYMENT",
    orbitLabel: "Unemployment",
  },
  {
    slug: "environment",
    title: "Agriculture & Environment",
    titleShort: "Environment",
    description: "Land, energy, and environment.",
    topics: ["environment", "agriculture"],
    // The Kalimati price series carries topic 'environment' but has its own
    // sector; without this carve-out it would appear in both, and every
    // indicator belongs to exactly one.
    excludePrefixes: ["KALIMATI_"],
    headlineCodes: ["ELECTRICITY_ACCESS"],
    orbitCode: "ELECTRICITY_ACCESS",
    orbitLabel: "Electricity access",
  },
  {
    slug: "governance",
    title: "Governance",
    titleShort: "Governance",
    description: "Public institutions and governance indicators.",
    topics: ["governance"],
    // Elections have their own sector (below). They share the `governance`
    // topic in the warehouse — the topic describes the subject, not the page —
    // so they are carved out here, the way Environment carves out Kalimati.
    excludePrefixes: ["ELECTION_"],
    // The WGI governance indicators are loaded (P2B.S3b); no curated headline
    // charts chosen yet, so the page shows the full list without an "At a glance".
    headlineCodes: [],
    // no orbitCode — the orbit node shows "in preparation"
  },
  {
    slug: "elections",
    title: "Elections",
    titleShort: "Elections",
    description:
      "How Nepal voted — results of the House of Representatives elections of 2026 and 2022, and of the 2022 local election that filled all 35,221 seats in Nepal's 753 local governments. Official figures from the Election Commission of Nepal.",
    topics: [],
    // Matched at runtime by code, the way Food Prices adopts the Kalimati series.
    includePrefixes: ["ELECTION_"],
    // No curated headline charts: the elections panel IS this page.
    headlineCodes: [],
    // No orbit number. Elections have no single headline figure — a seat count
    // belongs to a party, not to the country — and inventing one is exactly the
    // mistake the sector cards used to make.
    orbitNote: "results by party",
  },
  {
    slug: "disasters",
    title: "Disasters",
    titleShort: "Disasters",
    description:
      "Where and when disaster struck — every flood, landslide, fire and storm recorded by the National Disaster Risk Reduction and Management Authority since 2011, mapped at the place its own report gives, with what each one cost in lives and homes.",
    topics: [],
    // The disaster panel IS this page (DIS.S2); the indicators arrive in
    // DIS.S3, and will be matched by this prefix the way Kalimati is.
    includePrefixes: ["DISASTER_"],
    headlineCodes: [],
    // No orbit number, on purpose. Every other sector's node counts something
    // that is good to have more of. A death toll is not that, and animating one
    // upward on a landing page would be indecent.
    orbitNote: "what happened, and where",
  },
];

/** Source badge from a code alone (used where only the code is known — the orbit,
 *  headline cards). Prefer `sourceForIndicator` when the API row is available: it
 *  carries the authoritative source (decision 0005 / P2B.S4). */
export function sourceForCode(code: string): string {
  if (code.startsWith("NRB_BFS_")) return "Nepal Rastra Bank";
  if (code.startsWith("CENSUS_")) return "National Statistics Office";
  if (code.startsWith("KALIMATI_")) return "Kalimati Fruits and Vegetable Market Development Board";
  if (code.startsWith("ELECTION_")) return "Election Commission of Nepal";
  return "World Bank";
}

/** The indicator's own (origin) source — authoritative from the API, with the
 *  code heuristic as a fallback for older responses. */
export function sourceForIndicator(ind: IndicatorSummary): string {
  return ind.source ?? sourceForCode(ind.code);
}

/** True when this series is an alternative estimate: its own source is not the
 *  headline source for its concept (decision 0005). The UI badges these. */
export function isAlternative(ind: IndicatorSummary): boolean {
  return Boolean(ind.source && ind.preferred_source && ind.source !== ind.preferred_source);
}

function belongs(sector: SectorDef, ind: IndicatorSummary): boolean {
  if (sector.excludePrefixes?.some((p) => ind.code.startsWith(p))) return false;
  if (sector.topics.includes(ind.topic)) return true;
  if (sector.extraCodes?.includes(ind.code)) return true;
  if (sector.includePrefixes?.some((p) => ind.code.startsWith(p))) return true;
  return false;
}

/** Indicators belonging to one sector. Every indicator should match exactly
 *  one sector; `assignmentWarnings` surfaces orphans/doubles for the dev
 *  console (guards the P2B.S3 backfill). */
export function indicatorsForSector(
  sector: SectorDef,
  indicators: IndicatorSummary[],
): IndicatorSummary[] {
  return indicators.filter((ind) => belongs(sector, ind));
}

export const OTHER_THEME = "Everything else";

/** The part of an indicator name that says WHAT it measures.
 *
 *  World Bank names put the subject first and the unit or basis in brackets:
 *  "Trade in services (% of GDP)", "Broad money (% of GDP)", "Grants, excluding
 *  technical cooperation (BoP, current US$)". Matching the raw name therefore
 *  shelves half the catalogue by its DENOMINATOR — everything expressed as a
 *  share of GDP looks like national accounts. Dropping the bracketed part
 *  leaves the subject, which is what a reader is actually looking for. */
export function themeSubject(name: string): string {
  return name.toLowerCase().replace(/\([^)]*\)/g, " ");
}

/** Does this subject start a word with any of these terms?
 *
 *  Anchored at a word START, not a bare substring and not a whole word. A bare
 *  substring shelves the CPIA policy ratings under prices because "cpi" sits
 *  inside "cpia"; whole-word matching loses "taxes" and "banking" for "tax" and
 *  "bank". Word-start keeps the plurals and drops the accidents. */
function matchesAny(subject: string, terms: string[]): boolean {
  return terms.some((term) => {
    const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return new RegExp(`\\b${escaped}`).test(subject);
  });
}

export interface ThemeGroup {
  label: string;
  rows: IndicatorSummary[];
}

/** Shelve a sector's indicators into its themes, in the order the themes are
 *  declared. First match wins, so an indicator appears exactly once — the same
 *  rule that governs sector assignment, for the same reason: a number the
 *  reader meets twice under two headings is a number they cannot count.
 *
 *  Empty themes are dropped (an empty shelf is noise). Unmatched indicators are
 *  collected into a visible "Everything else" group placed last — never hidden,
 *  because a growing "Everything else" is exactly the signal that the themes
 *  need editing. */
export function groupByTheme(
  themes: ThemeDef[],
  indicators: IndicatorSummary[],
): ThemeGroup[] {
  const buckets = new Map<string, IndicatorSummary[]>(themes.map((t) => [t.label, []]));
  const other: IndicatorSummary[] = [];

  for (const ind of indicators) {
    const name = themeSubject(ind.name);
    const hit = themes.find((t) => matchesAny(name, t.match));
    if (hit) buckets.get(hit.label)!.push(ind);
    else other.push(ind);
  }

  const groups = themes
    .map((t) => ({ label: t.label, rows: buckets.get(t.label)! }))
    .filter((g) => g.rows.length > 0);
  if (other.length > 0) groups.push({ label: OTHER_THEME, rows: other });
  return groups;
}

export function sectorForCode(code: string, topic: string): SectorDef | undefined {
  const fake: IndicatorSummary = { code, topic, name: "", unit: "" };
  return SECTORS.find((s) => belongs(s, fake));
}

/** Dev-only integrity check: which indicators land in zero or multiple sectors. */
export function assignmentWarnings(indicators: IndicatorSummary[]): string[] {
  const warnings: string[] = [];
  for (const ind of indicators) {
    const hits = SECTORS.filter((s) => belongs(s, ind));
    if (hits.length === 0) warnings.push(`orphan: ${ind.code} (topic=${ind.topic})`);
    else if (hits.length > 1)
      warnings.push(`double: ${ind.code} -> ${hits.map((h) => h.slug).join(", ")}`);
  }
  return warnings;
}
