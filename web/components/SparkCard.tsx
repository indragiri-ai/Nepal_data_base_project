// One indicator as a compact card (P2B.S5 redesign): name, latest value, a tiny
// sparkline, and the source / "alternative estimate" badge. The sparkline is
// hand-drawn inline SVG — no chart library — so a grid of 150 cards stays cheap
// and out of the route's first-load JS.

import Link from "next/link";
import { formatCompact, formatValue } from "@/lib/format";
import { linkForCode } from "@/components/HeadlineChart";
import { sourceForIndicator, isAlternative } from "@/lib/sectors";
import type { IndicatorSummary, IndicatorSpark } from "@/lib/api";

/** A minimal sparkline: a normalized polyline in a fixed viewBox, no axes. A
 *  flat/single-point series renders a centred baseline rather than nothing. */
function Sparkline({ points }: { points: number[] }) {
  const W = 100;
  const H = 28;
  const pad = 3;
  if (points.length < 2) {
    return (
      <svg className="spark-svg" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
        <line x1="0" y1={H / 2} x2={W} y2={H / 2} className="spark-flat" />
      </svg>
    );
  }
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const stepX = W / (points.length - 1);
  const d = points
    .map((v, i) => {
      const x = i * stepX;
      const y = pad + (H - 2 * pad) * (1 - (v - min) / span);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg className="spark-svg" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
      <path d={d} className="spark-line" fill="none" />
    </svg>
  );
}

export default function SparkCard({
  ind,
  spark,
}: {
  ind: IndicatorSummary;
  spark: IndicatorSpark | undefined;
}) {
  const alt = isAlternative(ind);
  const source = sourceForIndicator(ind);
  const isCount = ind.unit === "COUNT" || ind.unit === "PERSONS";
  const value =
    spark && (isCount ? formatCompact(spark.latest_value) : formatValue(spark.latest_value, ind.unit));

  return (
    <Link href={linkForCode(ind.code)} className="spark-card">
      <span className="spark-name">{ind.name}</span>
      {spark ? (
        <>
          <span className="spark-val">
            {value}
            <span className="spark-period"> · {spark.latest_period}</span>
          </span>
          <Sparkline points={spark.points} />
        </>
      ) : (
        // Deliberately not "No data yet". A card reaches this branch for two
        // different reasons — the indicator has no observations at all, or it
        // has plenty but no single national figure (election results are
        // per-party; there is no one number for "seats won"). Claiming the data
        // is missing would be false in the second case, and the card cannot
        // tell the two apart. So it makes no claim about the data, and points
        // at the page that shows it properly.
        <span className="spark-val muted">See the series</span>
      )}
      {alt ? (
        <span className="badge alt" title={`Headline source for this measure: ${ind.preferred_source}`}>
          alternative estimate · {source}
        </span>
      ) : (
        <span className="badge">{source}</span>
      )}
    </Link>
  );
}
