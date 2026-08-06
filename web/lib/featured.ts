// What the landing page points at, as reviewable data.
//
// The front page had an orbit, sector cards and a trust section — all true, and
// none of it answers "what is actually good here?". A visitor who does not
// already know the portal has no reason to click any particular sector. These
// are the deliberate entry points: the few things worth someone's first two
// minutes.
//
// Rules for this list, so it does not rot into marketing:
//  * Every entry links somewhere that exists and has data behind it today.
//  * `note` describes what is there, in plain words, with no adjectives about
//    how good it is. Coverage and source, not praise.
//  * `fresh` marks a recent addition. Remove the flag when it stops being news
//    — a permanent "New" badge is a lie with a shelf life.

export interface FeaturedEntry {
  href: string;
  label: string;
  note: string;
  source: string;
  fresh?: boolean;
}

export const FEATURED: FeaturedEntry[] = [
  {
    href: "/economy",
    label: "Nepal's public finances",
    note: "What the federal government budgeted, collected, spent and owes, each year from FY 2017/18 to FY 2023/24.",
    source: "World Bank · MoF · FCGO",
  },
  {
    href: "/economy",
    label: "The seven provinces compared",
    note: "Revenue, spending and federal grants for every province — cross-checked against two provinces' own announced budgets.",
    source: "World Bank · Provincial MoFs",
    fresh: true,
  },
  {
    href: "/population",
    label: "Census 2021 on the map",
    note: "Population, density and literacy for all seven provinces and 77 districts, drawn from the national census.",
    source: "National Statistics Office",
  },
  {
    href: "/banking",
    label: "The banking system, month by month",
    note: "Lending rates, deposits, bad loans and mobile banking users, updated from the monthly statistics.",
    source: "Nepal Rastra Bank",
  },
];
