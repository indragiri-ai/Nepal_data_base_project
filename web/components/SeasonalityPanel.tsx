"use client";

// When is each vegetable cheap? (Kalimati seasonality)
//
// A decade of daily prices holds an answer no time-series chart can show:
// collapse every January into one number, every February into another, and the
// growing year appears. The market board's own site plots dates against prices
// and stops there — it cannot answer "when should I expect cauliflower to be
// cheap?", which is the question a shopper, a farmer or a journalist actually
// has.
//
// Dataviz method, applied:
//  * Form first. Twelve named periods compared on one measure is a bar chart,
//    and the bars stay in CALENDAR order — sorting them by price would destroy
//    the very thing being shown.
//  * One commodity at a time is one series, so one hue, no legend; the title
//    names it.
//  * The grid below is a sequential ramp in a SINGLE hue, light to dark. Each
//    row is scaled to its own range, because 20 rupees is dear for cabbage and
//    cheap for ginger — without that the grid would just rank vegetables by
//    price and say nothing about seasons.
//  * The grid is a real <table> with the number written in every cell, so
//    nothing rests on colour alone.

import { useEffect, useMemo, useState } from "react";
import EChart, { CHART_INK, TOOLTIP_STYLE, type ChartOption } from "@/components/EChart";
import { ApiError, fetchSeasonality, type SeasonalityResponse } from "@/lib/api";
import { downloadCsv } from "@/lib/csv";

const GEO = "NP0327101";
const CODE = "KALIMATI_PRICE_AVG";
const PRODUCE = "#008300";

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

// A month built from a handful of trading days is a weaker claim than one built
// from four hundred. Below this it is shown, but marked.
const THIN_MONTH_DAYS = 30;

const npr = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const npr1 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });

interface Row {
  commodity: string;
  /** Twelve slots, Jan..Dec. null where the market recorded nothing. */
  months: (number | null)[];
  days: number[];
  min: number;
  max: number;
}

function toRows(data: SeasonalityResponse): Row[] {
  const by = new Map<string, Row>();
  for (const p of data.points) {
    const row = by.get(p.breakdown_value) ?? {
      commodity: p.breakdown_value,
      months: Array<number | null>(12).fill(null),
      days: Array<number>(12).fill(0),
      min: Infinity,
      max: -Infinity,
    };
    row.months[p.month - 1] = p.mean_value;
    row.days[p.month - 1] = p.days;
    row.min = Math.min(row.min, p.mean_value);
    row.max = Math.max(row.max, p.mean_value);
    by.set(p.breakdown_value, row);
  }
  return [...by.values()].sort((a, b) => a.commodity.localeCompare(b.commodity));
}

/** 0 = this commodity's cheapest month, 1 = its dearest. Scaled per ROW on
 *  purpose: the grid is about seasons, not about which vegetable costs more. */
function intensity(row: Row, value: number | null): number | null {
  if (value === null || row.max === row.min) return value === null ? null : 0.5;
  return (value - row.min) / (row.max - row.min);
}

export default function SeasonalityPanel() {
  const [data, setData] = useState<SeasonalityResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [commodity, setCommodity] = useState("Tomato Small(Local)");

  useEffect(() => {
    let cancelled = false;
    fetchSeasonality(CODE, GEO, "commodity")
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(
            e instanceof ApiError ? e.message : "Could not load the seasonal averages.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const rows = useMemo(() => (data ? toRows(data) : []), [data]);
  const selected = rows.find((r) => r.commodity === commodity) ?? rows[0];

  const option: ChartOption | null = useMemo(() => {
    if (!selected) return null;
    return {
      grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true },
      tooltip: {
        ...TOOLTIP_STYLE,
        trigger: "item",
        formatter: (p) => {
          const i = (p as { dataIndex: number }).dataIndex;
          const v = selected.months[i];
          if (v === null) return `${MONTHS[i]}: not recorded`;
          return (
            `<strong>${MONTHS[i]}</strong><br/>` +
            `NPR ${npr1.format(v)} per kg<br/>` +
            `averaged over ${selected.days[i].toLocaleString()} trading days`
          );
        },
      },
      xAxis: {
        type: "category",
        data: MONTHS,
        axisLabel: { color: CHART_INK.axisLabel, fontSize: 11 },
        axisLine: { lineStyle: { color: CHART_INK.axisLine } },
        axisTick: { show: false },
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
          type: "bar",
          name: selected.commodity,
          data: selected.months,
          barMaxWidth: 34,
          itemStyle: { color: PRODUCE, borderRadius: [4, 4, 0, 0] },
        },
      ],
    };
  }, [selected]);

  const cheapest = selected
    ? MONTHS[selected.months.indexOf(selected.min)]
    : null;
  const dearest = selected ? MONTHS[selected.months.indexOf(selected.max)] : null;

  return (
    <section className="fiscal-panel" aria-labelledby="seasonality">
      <div className="band-head">
        <h2 id="seasonality">When is it cheapest?</h2>
        {rows.length > 0 && (
          <button
            type="button"
            className="btn ghost small"
            onClick={() =>
              downloadCsv("kalimati-seasonality.csv", [
                ["Commodity", ...MONTHS.map((m) => `${m} (NPR/kg)`)],
                ...rows.map((r) => [
                  r.commodity,
                  ...r.months.map((v) => (v === null ? "" : npr1.format(v))),
                ]),
              ])
            }
          >
            Download CSV
          </button>
        )}
      </div>

      <p className="sub">
        Every January in the series averaged into one number, every February into
        another, and so on — a decade of daily prices folded into a single
        growing year. A price chart cannot show this, and the market
        board&rsquo;s own site does not attempt it.
      </p>

      {error && (
        <div className="state error" role="status">
          {error}
        </div>
      )}
      {!error && !data && <p className="state">Loading seasonal averages…</p>}

      {selected && option && (
        <>
          <div className="controls">
            <label className="field">
              Commodity
              <select
                className="filter-field"
                value={selected.commodity}
                onChange={(e) => setCommodity(e.target.value)}
              >
                {rows.map((r) => (
                  <option key={r.commodity} value={r.commodity}>
                    {r.commodity}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <figure className="panel">
            <figcaption>
              <h3>{selected.commodity} — average price by month of the year</h3>
              <p>
                Cheapest in <strong>{cheapest}</strong> at NPR{" "}
                {npr1.format(selected.min)}, dearest in <strong>{dearest}</strong>{" "}
                at NPR {npr1.format(selected.max)} — a difference of{" "}
                <strong>
                  {Math.round(((selected.max - selected.min) / selected.min) * 100)}%
                </strong>
                .
              </p>
            </figcaption>
            <EChart
              option={option}
              height={280}
              ariaLabel={`Bar chart of ${selected.commodity} average wholesale price for each month of the year: ${MONTHS.map(
                (m, i) =>
                  `${m} ${selected.months[i] === null ? "not recorded" : npr1.format(selected.months[i]!)}`,
              ).join(", ")} NPR per kg.`}
            />
          </figure>

          <h3 className="grid-head">The whole year, every vegetable</h3>
          <p className="sub">
            Each row is shaded against <em>its own</em> cheapest and dearest
            month — darker means dearer <em>for that vegetable</em>. Read across
            a row to see one vegetable&rsquo;s season; read down a column to see
            what is cheap in a given month. Figures are NPR per kg.
          </p>
          <div className="table-wrap">
            <table className="data season-grid">
              <caption className="sr-only">
                Average wholesale price by commodity and month of the year, NPR per
                kilogram
              </caption>
              <thead>
                <tr>
                  <th scope="col">Commodity</th>
                  {MONTHS.map((m) => (
                    <th key={m} scope="col">
                      {m}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.commodity}>
                    <th scope="row">{r.commodity}</th>
                    {r.months.map((v, i) => {
                      const t = intensity(r, v);
                      return (
                        <td
                          key={i}
                          style={
                            t === null
                              ? undefined
                              : { backgroundColor: `rgba(0, 131, 0, ${0.06 + t * 0.46})` }
                          }
                          title={
                            v === null
                              ? `${r.commodity}, ${MONTHS[i]}: not recorded`
                              : `${r.commodity}, ${MONTHS[i]}: NPR ${npr1.format(v)} per kg, from ${r.days[i].toLocaleString()} trading days`
                          }
                        >
                          {v === null ? "—" : npr.format(v)}
                          {v !== null && r.days[i] < THIN_MONTH_DAYS && (
                            <span className="thin" aria-label="few trading days">
                              *
                            </span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="fiscal-provenance">
            <strong>Source:</strong> {data?.provenance.source}. Averages are of
            the market board&rsquo;s own published daily average, 2013 to the
            present, grouped by calendar month. A <span className="thin">*</span>{" "}
            marks a month averaged from fewer than {THIN_MONTH_DAYS} trading days
            across the whole decade — shown, but resting on less. Months the
            market never recorded are left blank rather than filled in.
          </p>
        </>
      )}
    </section>
  );
}
