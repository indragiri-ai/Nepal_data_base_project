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
  mapCard?: { href: string; label: string; note: string };
  orbitCode?: string; // ONE code whose latest value shows on the orbit node
  external?: { href: string; label: string };
}

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
    orbitCode: "GDP_GROWTH",
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
    external: { href: "/banking", label: "Open the full banking dashboard" },
  },
  {
    slug: "people",
    title: "People & Population",
    titleShort: "People",
    description:
      "Who lives in Nepal, where, and how that is changing — census counts and demographic series.",
    topics: ["population"],
    headlineCodes: ["POP_TOTAL", "POP_GROWTH", "URBAN_POP_PCT"],
    orbitCode: "CENSUS_POP_TOTAL",
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
  },
  {
    slug: "education",
    title: "Education",
    titleShort: "Education",
    description:
      "Literacy and schooling — how Nepal learns, from census counts and international series.",
    topics: ["education"],
    headlineCodes: ["ADULT_LITERACY", "SCHOOL_ENROLL_PRIMARY"],
    orbitCode: "ADULT_LITERACY",
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
  },
  {
    slug: "environment",
    title: "Agriculture & Environment",
    titleShort: "Environment",
    description: "Land, energy, and environment.",
    topics: ["environment", "agriculture"],
    headlineCodes: ["ELECTRICITY_ACCESS"],
    orbitCode: "ELECTRICITY_ACCESS",
  },
  {
    slug: "governance",
    title: "Governance",
    titleShort: "Governance",
    description: "Public institutions and governance indicators.",
    topics: ["governance"],
    headlineCodes: [], // none loaded yet — arrives with the full WB catalog (P2B.S3)
    // no orbitCode — the orbit node shows "in preparation"
  },
];

/** Source badge for a code, until P2B.S4 formalizes preferred sources. */
export function sourceForCode(code: string): string {
  if (code.startsWith("NRB_BFS_")) return "Nepal Rastra Bank";
  if (code.startsWith("CENSUS_")) return "National Statistics Office";
  return "World Bank";
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
