"use client";

// One curated chart in a sector's "At a glance" band: the indicator name (a
// link into the full explorer/dashboard), the latest value, and a small trend.
// The chart itself is lazy-loaded so ECharts stays out of the sector page's
// first-load JS (spec trap #1).

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchSeries, type DataResponse } from "@/lib/api";
import { ApiError } from "@/lib/api";
import { formatCompact, formatValue } from "@/lib/format";
import { latestPair } from "@/lib/latest";
import { sourceForCode } from "@/lib/sectors";

const TrendChart = dynamic(() => import("@/components/TrendChart"), {
  ssr: false,
  loading: () => <div className="skeleton headline-chart-skel" aria-hidden="true" />,
});

/** Where an indicator's detail lives: NRB series open the banking dashboard,
 *  everything else the annual explorer. */
export function linkForCode(code: string): string {
  return code.startsWith("NRB_BFS_")
    ? `/banking?indicator=${encodeURIComponent(code)}`
    : `/explore?indicator=${encodeURIComponent(code)}`;
}

/** Keep only the headline slice of a multi-breakdown series: the aggregate
 *  bank class, or the empty-breakdown (all-sexes) rows. Returns a copy. */
function headlineSlice(data: DataResponse): DataResponse {
  const hasBfi = data.observations.some((o) => o.breakdowns?.bfi_class);
  const hasSex = data.observations.some((o) => o.breakdowns?.sex);
  if (!hasBfi && !hasSex) return data;

  let obs = data.observations;
  if (hasBfi) {
    const classes = new Set(obs.map((o) => o.breakdowns?.bfi_class ?? ""));
    const pick = classes.has("overall")
      ? "overall"
      : classes.has("commercial_banks")
        ? "commercial_banks"
        : null;
    if (pick) obs = obs.filter((o) => (o.breakdowns?.bfi_class ?? "") === pick);
  }
  if (hasSex) {
    obs = obs.filter((o) => Object.keys(o.breakdowns ?? {}).length === 0);
  }
  return { ...data, observations: obs };
}

export default function HeadlineChart({ code }: { code: string }) {
  const [data, setData] = useState<DataResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    fetchSeries(code, "NP")
      .then((d) => {
        if (!cancelled) setData(headlineSlice(d));
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof ApiError ? e.message : "Could not load this series.");
      });
    return () => {
      cancelled = true;
    };
  }, [code]);

  if (error) {
    return (
      <div className="state error headline-state" role="status">
        {error}
      </div>
    );
  }
  if (!data) {
    return <div className="skeleton headline-chart-skel" aria-hidden="true" />;
  }

  const pair = latestPair(data);
  const source = sourceForCode(code);
  const isCount = data.unit_code === "COUNT" || data.unit_code === "PERSONS";

  return (
    <div className="headline">
      <Link href={linkForCode(code)} className="headline-name">
        {data.indicator.name}
      </Link>
      {pair && (
        <p className="headline-value">
          {isCount ? formatCompact(pair.latest) : formatValue(pair.latest, data.unit_code)}
          <span className="headline-period"> · {pair.period}</span>
        </p>
      )}
      <TrendChart data={data} height={200} compact />
      <p className="headline-source">
        {source} · {pair?.period ?? "latest"}
      </p>
    </div>
  );
}
