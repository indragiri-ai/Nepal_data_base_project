// Shared "latest observation" logic for stat tiles and the orbit nodes.
// Prefers the aggregate breakdown when a series carries one (NRB series have a
// bfi_class; interest-rate series exist only for commercial_banks — see spec
// trap #4), so a headline number is never an arbitrary sub-series.

import type { DataResponse } from "@/lib/api";

export interface LatestPair {
  latest: number;
  prev: number | null;
  period: string;
}

export function latestPair(data: DataResponse): LatestPair | null {
  let obs = data.observations;

  // Banking series carry a bfi_class — take the aggregate class.
  const classes = new Set(obs.map((o) => o.breakdowns?.bfi_class ?? ""));
  const pick = classes.has("overall")
    ? "overall"
    : classes.has("commercial_banks")
      ? "commercial_banks"
      : null;
  if (pick !== null) {
    obs = obs.filter((o) => (o.breakdowns?.bfi_class ?? "") === pick);
  }

  // Census series carry a sex breakdown (male/female/total) — the headline is
  // the total, stored as the empty-breakdown row. Without this the orbit shows
  // a single sex's count (e.g. ~14.9M instead of 29.2M).
  if (obs.some((o) => o.breakdowns?.sex)) {
    obs = obs.filter((o) => Object.keys(o.breakdowns ?? {}).length === 0);
  }

  if (obs.length === 0) return null;
  const last = obs[obs.length - 1];
  const prev = obs.length > 1 ? obs[obs.length - 2].value : null;
  return { latest: last.value, prev, period: last.period };
}
