"use client";

// Kalimati daily wholesale prices (ODN.S2) — what food actually cost, day by
// day, for a decade.
//
// Dataviz method, applied:
//  * Form first. This is change over time, so it is a line chart. But the
//    source publishes a RANGE per day (a low and a high), not a point, so the
//    chart draws the range as a band with the midpoint on top. Drawing only a
//    single line would quietly throw away half of what the market published.
//  * One commodity on screen = ONE entity, so one hue. The band and the line
//    are the same entity shown two ways, so they share it and separate by
//    fill vs stroke — never by a second colour.
//  * The midpoint is DERIVED here, not stored, and never called an average:
//    it is exactly (low + high) / 2, and the market board's own published
//    average is a different, usually higher number.
//  * Daily/monthly is a readability toggle. The monthly band shows the
//    month's CHEAPEST and DEAREST price, not an average of each end —
//    averaging both ends collapses the band and hides the volatility that is
//    the whole story of a vegetable market.
//  * Table view and CSV below; identity never rests on colour alone.
//
// Vintage honesty: this series ENDS 18 April 2022. Every label says so, because
// a decade-old price shown without its date is a wrong answer to "what does
// this cost?".

import { useEffect, useMemo, useState } from "react";
import EChart, { CHART_INK, TOOLTIP_STYLE, type ChartOption } from "@/components/EChart";
import { ApiError, fetchSeriesSlice, type DataResponse } from "@/lib/api";
import { downloadCsv } from "@/lib/csv";

const GEO = "NP0327101"; // Kathmandu Metropolitan City — where the market is
const MIN_CODE = "KALIMATI_PRICE_MIN";
const MAX_CODE = "KALIMATI_PRICE_MAX";
// The market board's OWN average, taken from the board directly. It reaches
// today, where the low/high pair (re-published via Open Data Nepal) stops in
// April 2022. It is a genuine average, NOT the midpoint of low and high: the
// two differ on 46% of the days where both exist.
const AVG_CODE = "KALIMATI_PRICE_AVG";

// The portal's validated categorical palette (globals.css). Produce gets
// series-1; the band is the same hue at low opacity, not a second colour.
const PRODUCE = "#008300";
const BAND = "rgba(0, 131, 0, 0.30)";

// The curated basket, in the order the loader ranked it (most trading days
// first). Kept in step with db/seeds/kalimati_basket.csv.
const BASKET = [
  "Cauli Local", "Ginger", "Cabbage(Local)", "Raddish White(Local)", "Chilli Dry",
  "Potato Red", "Bamboo Shoot", "Onion Dry (Indian)", "Brd Leaf Mustard",
  "Coriander Green", "French Bean(Local)", "Tomato Small(Local)", "Carrot(Local)",
  "Onion Green", "Spinach Leaf", "Brinjal Long", "Chilli Green",
  "Garlic Dry Chinese", "Mushroom(Kanya)", "Lime", "Capsicum", "Pumpkin",
  "Tamarind", "Bottle Gourd", "Tofu",
] as const;

type Grain = "daily" | "monthly";

interface Point {
  label: string;
  /** The day's low and high are absent after 2022-04-18, where the
   *  re-published series ends and only the board's own average continues. */
  low: number | null;
  high: number | null;
  /** The market board's own published average. Daily: as published. Monthly:
   *  the mean of that month's daily averages. */
  mid: number;
}

/** How much of the decade to show at once. Nine years of a seasonal series in
 *  one width is a comb; most questions are about the recent years. */
type Window = "all" | "3y";
const WINDOWS: Record<Window, string> = { "3y": "Last 3 years", all: "All years" };

const npr = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

/** Roll daily prices up to months.
 *
 *  The band becomes the month's REAL spread — its cheapest low and its dearest
 *  high — and the line the average of that month's daily midpoints.
 *
 *  The first version averaged the lows and averaged the highs, which was a
 *  quiet mistake: averaging both ends collapses the band to almost nothing, so
 *  the chart drew a hairline and the whole point of showing a range was lost.
 *  A month in which tomatoes swung between 20 and 80 rupees should LOOK like
 *  that month. */
function toMonthly(points: Point[]): Point[] {
  interface Bucket {
    low: number | null;
    high: number | null;
    midSum: number;
    n: number;
  }
  const buckets = new Map<string, Bucket>();
  for (const p of points) {
    const month = p.label.slice(0, 7); // YYYY-MM
    const b = buckets.get(month) ?? { low: null, high: null, midSum: 0, n: 0 };
    // A month keeps a band only from the days that HAVE one; months after the
    // low/high series ends get no band at all rather than a partial one.
    if (p.low !== null) b.low = b.low === null ? p.low : Math.min(b.low, p.low);
    if (p.high !== null) b.high = b.high === null ? p.high : Math.max(b.high, p.high);
    b.midSum += p.mid;
    b.n += 1;
    buckets.set(month, b);
  }
  return [...buckets.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([month, b]) => ({
      label: month,
      low: b.low,
      high: b.high,
      mid: b.midSum / b.n,
    }));
}

export default function MarketPricesPanel() {
  const [commodity, setCommodity] = useState<string>("Tomato Small(Local)");
  const [grain, setGrain] = useState<Grain>("monthly");
  const [windowSize, setWindowSize] = useState<Window>("3y");
  const [raw, setRaw] = useState<Point[] | null>(null);
  const [meta, setMeta] = useState<DataResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showTable, setShowTable] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setRaw(null);
    setError(null);
    Promise.all([
      fetchSeriesSlice(AVG_CODE, GEO, "commodity", commodity),
      fetchSeriesSlice(MIN_CODE, GEO, "commodity", commodity).catch(() => null),
      fetchSeriesSlice(MAX_CODE, GEO, "commodity", commodity).catch(() => null),
    ])
      .then(([avgs, lows, highs]) => {
        if (cancelled) return;
        // The AVERAGE drives the timeline: it is the longest series, running to
        // today. Low/high are attached where they exist and left null after
        // April 2022 — the band simply stops rather than being extended with a
        // number nobody published. (Low/high are optional: a commodity the
        // board still trades may have no re-published history at all.)
        const lowByDay = new Map((lows?.observations ?? []).map((o) => [o.period, o.value]));
        const highByDay = new Map((highs?.observations ?? []).map((o) => [o.period, o.value]));
        const points: Point[] = avgs.observations.map((o) => {
          const low = lowByDay.get(o.period);
          const high = highByDay.get(o.period);
          // A low without its high is half a band; take neither.
          const paired = low !== undefined && high !== undefined;
          return {
            label: o.period,
            low: paired ? low : null,
            high: paired ? high : null,
            mid: o.value,
          };
        });
        setRaw(points);
        setMeta(avgs);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(
            e instanceof ApiError ? e.message : "Could not load the price series.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [commodity]);

  const points = useMemo(() => {
    if (raw === null) return [];
    // Window first, then roll up: a 3-year monthly view should be built from
    // the days inside those 3 years, not sliced out of the full rollup.
    let rows = raw;
    if (windowSize === "3y" && raw.length > 0) {
      const lastDay = raw[raw.length - 1].label;
      const cutoff = `${Number(lastDay.slice(0, 4)) - 3}${lastDay.slice(4)}`;
      rows = raw.filter((p) => p.label >= cutoff);
    }
    return grain === "monthly" ? toMonthly(rows) : rows;
  }, [raw, grain, windowSize]);

  // The band means something different in each view, so it is named for what
  // it actually is rather than carrying one vague label across both.
  const rangeLabel = grain === "monthly" ? "Cheapest to dearest in the month" : "Low to high";
  // Always the market board's own figure, so it is named after them rather
  // than described vaguely as "average" — the word the source misuses.
  const midLabel = "Market board average";

  const option: ChartOption | null = useMemo(() => {
    if (points.length === 0) return null;
    const labels = points.map((p) => p.label);
    const lows = points.map((p) => p.low);
    // The band is drawn as a transparent floor plus a stacked height, which is
    // how a two-bounded range is filled. The tooltip below reads the real
    // numbers out of `points`, never off the stack.
    // null where the day has no published low/high: ECharts leaves a gap
    // instead of drawing a band across data that does not exist.
    const spans = points.map((p) =>
      p.low === null || p.high === null ? null : p.high - p.low,
    );
    const mids = points.map((p) => p.mid);

    return {
      grid: { left: 8, right: 24, top: 40, bottom: 8, containLabel: true },
      legend: {
        data: [rangeLabel, midLabel],
        top: 0,
        // Right-aligned: the y-axis name sits at the top LEFT of the plot, and
        // a left-aligned legend printed straight through it.
        right: 0,
        icon: "roundRect",
        textStyle: { color: CHART_INK.secondary, fontSize: 12 },
      },
      tooltip: {
        ...TOOLTIP_STYLE,
        trigger: "axis",
        axisPointer: {
          type: "line",
          lineStyle: { color: CHART_INK.axisLine, type: "dashed", width: 1 },
        },
        formatter: (params) => {
          const list = Array.isArray(params) ? params : [params];
          const i = list[0]?.dataIndex as number;
          const p = points[i];
          if (!p) return "";
          const top = grain === "monthly" ? "dearest" : "high";
          const bottom = grain === "monthly" ? "cheapest" : "low";
          const band =
            p.low === null || p.high === null
              ? "<em>no low/high published for this period</em><br/>"
              : `${top} &nbsp;NPR ${npr.format(p.high)}<br/>` +
                `${bottom} &nbsp;NPR ${npr.format(p.low)}<br/>`;
          return (
            `<strong>${p.label}</strong><br/>` +
            band +
            `board average &nbsp;NPR ${npr.format(p.mid)}`
          );
        },
      },
      xAxis: {
        type: "category",
        data: labels,
        boundaryGap: false,
        axisLabel: { color: CHART_INK.axisLabel, fontSize: 11, hideOverlap: true },
        axisLine: { lineStyle: { color: CHART_INK.axisLine } },
      },
      yAxis: {
        type: "value",
        name: "NPR per kg",
        nameTextStyle: { color: CHART_INK.axisLabel, fontSize: 11, align: "left" },
        axisLabel: { color: CHART_INK.axisLabel, fontSize: 11 },
        splitLine: { lineStyle: { color: CHART_INK.grid } },
      },
      series: [
        {
          // Invisible floor of the band.
          name: "band-floor",
          type: "line",
          stack: "range",
          data: lows,
          lineStyle: { opacity: 0 },
          itemStyle: { opacity: 0 },
          symbol: "none",
          silent: true,
          tooltip: { show: false },
          z: 1,
        },
        {
          name: rangeLabel,
          type: "line",
          stack: "range",
          data: spans,
          lineStyle: { opacity: 0 },
          areaStyle: { color: BAND },
          symbol: "none",
          silent: true,
          z: 1,
        },
        {
          name: midLabel,
          type: "line",
          data: mids,
          lineStyle: { color: PRODUCE, width: 1.5 },
          itemStyle: { color: PRODUCE },
          symbol: "none",
          smooth: false,
          z: 2,
        },
      ],
    };
  }, [points]);

  // How many periods still have a low/high band, for the caption.
  const banded = points.filter((p) => p.low !== null).length;
  const first = points[0];
  const last = points[points.length - 1];

  return (
    <section className="fiscal-panel" aria-labelledby="market-prices">
      <div className="band-head">
        <h2 id="market-prices">What food cost at Kalimati market</h2>
        {points.length > 0 && (
          <button
            type="button"
            className="btn ghost small"
            onClick={() =>
              downloadCsv(
                `kalimati-${commodity.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}-${grain}.csv`,
                [
                  [grain === "monthly" ? "Month" : "Date", `${grain === "monthly" ? "Cheapest" : "Low"} (NPR/kg)`,
                   `${grain === "monthly" ? "Dearest" : "High"} (NPR/kg)`,
                   `${midLabel} (NPR/kg)`],
                  ...points.map((p) => [
                    p.label,
                    p.low === null ? "" : npr.format(p.low),
                    p.high === null ? "" : npr.format(p.high),
                    npr.format(p.mid),
                  ]),
                ],
              )
            }
          >
            Download CSV
          </button>
        )}
      </div>

      <p className="sub">
        Wholesale prices at the Kalimati Fruits and Vegetable Market in
        Kathmandu — Nepal&rsquo;s largest wholesale produce market. The line is
        the market board&rsquo;s own average, published daily and current. The
        shaded band is the day&rsquo;s lowest and highest price, which comes
        from a re-published copy that <strong>stops on 18 April 2022</strong> —
        so the band ends there while the line continues.
      </p>

      <div className="controls">
        <label className="field">
          Commodity
          <select
            className="filter-field"
            value={commodity}
            onChange={(e) => setCommodity(e.target.value)}
          >
            {BASKET.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <div className="segmented" role="group" aria-label="Time detail">
          <button
            type="button"
            aria-pressed={grain === "monthly"}
            onClick={() => setGrain("monthly")}
          >
            Monthly
          </button>
          <button
            type="button"
            aria-pressed={grain === "daily"}
            onClick={() => setGrain("daily")}
          >
            Every day
          </button>
        </div>
        <div className="segmented" role="group" aria-label="How many years">
          {(Object.keys(WINDOWS) as Window[]).map((w) => (
            <button
              key={w}
              type="button"
              aria-pressed={windowSize === w}
              onClick={() => setWindowSize(w)}
            >
              {WINDOWS[w]}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="state error" role="status">
          {error}
        </div>
      )}
      {!error && raw === null && <p className="state">Loading prices…</p>}

      {option && first && last && (
        <>
          <figure className="panel">
            <figcaption>
              <h3>
                {commodity} — {grain === "monthly" ? "monthly" : "daily"} wholesale
                price, {first.label} to {last.label}
              </h3>
              <p>
                {grain === "monthly" ? (
                  <>
                    The line is the market board&rsquo;s own average for each
                    month; the shaded band, where it appears, spans the cheapest
                    and dearest price recorded that month. Over these{" "}
                    {points.length.toLocaleString()} months the average ranged{" "}
                    <strong>
                      NPR {npr.format(Math.min(...points.map((p) => p.mid)))} to{" "}
                      {npr.format(Math.max(...points.map((p) => p.mid)))} per kg
                    </strong>
                    .
                  </>
                ) : (
                  <>
                    The line is the market board&rsquo;s published average for
                    each trading day; the shaded band, where it appears, is that
                    day&rsquo;s low to high. {points.length.toLocaleString()}{" "}
                    trading days shown.
                  </>
                )}
                {banded > 0 && banded < points.length && (
                  <>
                    {" "}
                    The band covers the first {banded.toLocaleString()} of them —
                    the low/high series ends 18 April 2022.
                  </>
                )}
              </p>
            </figcaption>
            <EChart
              option={option}
              height={340}
              ariaLabel={`Line chart of ${commodity} wholesale prices at Kalimati market, ${first.label} to ${last.label}, in NPR per kilogram. A shaded band shows each period's low-to-high range with a midpoint line through it.`}
            />
          </figure>

          <button
            type="button"
            className="btn ghost small"
            aria-expanded={showTable}
            onClick={() => setShowTable((v) => !v)}
          >
            {showTable ? "Hide table" : "View table"}
          </button>
          {showTable && (
            <div className="table-wrap">
              <table className="data">
                <caption className="sr-only">
                  {commodity} wholesale prices, NPR per kilogram
                </caption>
                <thead>
                  <tr>
                    <th scope="col">{grain === "monthly" ? "Month" : "Date"}</th>
                    <th scope="col">{grain === "monthly" ? "Cheapest" : "Low"}</th>
                    <th scope="col">{grain === "monthly" ? "Dearest" : "High"}</th>
                    <th scope="col">{midLabel}</th>
                  </tr>
                </thead>
                <tbody>
                  {/* Newest first, and capped: a decade of daily rows is not a
                      table anyone reads. The CSV carries the whole series. */}
                  {[...points].reverse().slice(0, 120).map((p) => (
                    <tr key={p.label}>
                      <th scope="row">{p.label}</th>
                      <td>{p.low === null ? "—" : npr.format(p.low)}</td>
                      <td>{p.high === null ? "—" : npr.format(p.high)}</td>
                      <td>{npr.format(p.mid)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {points.length > 120 && (
                <p className="sub">
                  Showing the most recent 120 of {points.length.toLocaleString()}{" "}
                  rows — download the CSV for all of them.
                </p>
              )}
            </div>
          )}

          <p className="fiscal-provenance">
            <strong>Source:</strong> Kalimati Fruits and Vegetable Market
            Development Board (kalimatimarket.gov.np), the market that records
            these prices. The <strong>average line</strong> is the board&rsquo;s
            own published figure, taken directly from them, and runs to the
            present. The <strong>low/high band</strong> comes from the board&rsquo;s
            data as re-published by <strong>Open Data Nepal</strong> under
            CC BY 4.0, which ends 18 April 2022. The two are kept apart on
            purpose: the board&rsquo;s average is a real average, not the
            midpoint of the low and high, and the two differ on 46% of the days
            where both exist. Prices are per kilogram; the market also publishes
            some commodities per piece or per dozen, and those are deliberately
            not shown because converting them would need a weight the source
            does not give. Coverage 16 June 2013 to the present
            {meta?.provenance.latest_release_date
              ? `; loaded ${meta.provenance.latest_release_date}`
              : ""}
            .
          </p>
        </>
      )}
    </section>
  );
}
