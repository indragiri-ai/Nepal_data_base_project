"use client";

// Province comparison (WBF.S2 provincial) — what each of Nepal's seven
// provinces raises, receives and spends. Per-province budgets are hard to find
// anywhere, which is exactly why they belong on a page and not only in a table.
//
// Dataviz method, applied:
//  * Form first. This compares SEVEN named entities on ONE measure at ONE
//    point in time — magnitude across categories, not change over time. That
//    is a bar chart, horizontal so the province names read left-to-right at
//    full length instead of being rotated or truncated. The federal panel
//    above uses lines because its job is change over time; same page, different
//    job, different form.
//  * One measure on screen at a time, so this is a SINGLE series and takes a
//    single hue — not seven. Seven categorical hues would encode identity that
//    the axis labels already carry, and would burn the whole palette on one
//    chart. The hue follows the MEASURE, matching the federal panel's entity
//    colours (revenue green, expenditure blue, grants amber), so a reader who
//    learns the colours upstairs keeps them here.
//  * A single series carries no legend — the title names it.
//  * Bars are sorted by value, so rank is read off position, not guessed.
//  * Table view + CSV below: identity and value never depend on colour alone.
//
// Stored in NPR million, shown in NPR billion (an exact /1000), labelled.

import { useEffect, useMemo, useState } from "react";
import EChart, { CHART_INK, TOOLTIP_STYLE, type ChartOption } from "@/components/EChart";
import { ApiError, fetchGeoValues, type GeoDataResponse } from "@/lib/api";
import { downloadCsv } from "@/lib/csv";

type Measure = "REVENUE" | "EXPENDITURE" | "GRANTS";
type Basis = "ACTUAL" | "BUDGET";

// Hue per measure, matching the federal panel's entity colours (globals.css
// --series-1/2/3). Assigned by entity, never by rank: switching Actual/Budget
// must not repaint the chart, because it is the same entity measured twice.
const MEASURES: Record<
  Measure,
  { label: string; colour: string; blurb: string; noun: string }
> = {
  REVENUE: {
    label: "Revenue and grants",
    colour: "#008300",
    noun: "received",
    blurb:
      "Everything a province takes in: its own taxes and other revenue, plus the grants it receives from the federal government.",
  },
  EXPENDITURE: {
    label: "Expenditure",
    colour: "#2a78d6",
    noun: "spent",
    blurb:
      "Recurrent plus capital spending. Recurrent here includes the money a province passes down to its local governments.",
  },
  GRANTS: {
    label: "Grants received",
    colour: "#c98500",
    noun: "received in grants",
    blurb:
      "Transfers from the federal government — equalization, conditional, complementary and special grants.",
  },
};

const BASES: Record<Basis, string> = { ACTUAL: "Actual", BUDGET: "Budget" };

const toBn = (millions: number) => millions / 1000;
// Always one decimal, never zero or two: these numbers are read as a column
// against each other, and "44.5" beside "28" makes the eye compare ragged
// strings instead of magnitudes.
const bn = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

export default function ProvincePanel() {
  const [measure, setMeasure] = useState<Measure>("EXPENDITURE");
  const [basis, setBasis] = useState<Basis>("ACTUAL");
  const [data, setData] = useState<GeoDataResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showTable, setShowTable] = useState(false);

  const code = `FISCAL_PROV_${measure}_${basis}`;

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    fetchGeoValues(code, "province")
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(
            e instanceof ApiError
              ? e.message
              : "Could not load the provincial figures.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [code]);

  // Ascending, because ECharts draws a horizontal bar axis bottom-up: the
  // largest province ends up at the TOP of the chart, where a reader looks first.
  const sorted = useMemo(
    () => (data ? [...data.values].sort((a, b) => a.value - b.value) : []),
    [data],
  );

  const option: ChartOption | null = useMemo(() => {
    if (sorted.length === 0) return null;
    const spec = MEASURES[measure];
    return {
      grid: { left: 8, right: 64, top: 8, bottom: 8, containLabel: true },
      tooltip: {
        ...TOOLTIP_STYLE,
        trigger: "item",
        valueFormatter: (v) => (v == null ? "—" : `NPR ${bn.format(v as number)} bn`),
      },
      xAxis: {
        type: "value",
        axisLabel: { color: CHART_INK.axisLabel, fontSize: 11 },
        splitLine: { lineStyle: { color: CHART_INK.grid } },
      },
      yAxis: {
        type: "category",
        data: sorted.map((v) => v.name),
        axisLabel: { color: CHART_INK.text, fontSize: 12 },
        axisLine: { lineStyle: { color: CHART_INK.axisLine } },
        axisTick: { show: false },
      },
      series: [
        {
          type: "bar",
          name: spec.label,
          data: sorted.map((v) => toBn(v.value)),
          // Thin marks with a 4px rounded data-end; the flat end stays anchored
          // to the zero baseline so bar length reads as magnitude.
          barMaxWidth: 18,
          barCategoryGap: "40%",
          itemStyle: { color: spec.colour, borderRadius: [0, 4, 4, 0] },
          label: {
            show: true,
            position: "right",
            // Text wears ink tokens, never the series colour.
            color: CHART_INK.secondary,
            fontSize: 11,
            formatter: (p) => bn.format(p.value as number),
          },
        },
      ],
    };
  }, [sorted, measure]);

  const spec = MEASURES[measure];
  const top = sorted.length > 0 ? sorted[sorted.length - 1] : null;
  const bottom = sorted.length > 0 ? sorted[0] : null;

  const tableRows = useMemo(
    () =>
      [...sorted]
        .reverse()
        .map((v) => [v.name, bn.format(toBn(v.value))] as string[]),
    [sorted],
  );

  return (
    <section className="fiscal-panel" aria-labelledby="province-finance">
      <div className="band-head">
        <h2 id="province-finance">The seven provinces compared</h2>
        {data && (
          <button
            type="button"
            className="btn ghost small"
            onClick={() =>
              downloadCsv(`nepal-provincial-${measure.toLowerCase()}-${basis.toLowerCase()}.csv`, [
                ["Province", `${spec.label} (${BASES[basis]}), NPR billion`, "Fiscal year"],
                ...[...sorted]
                  .reverse()
                  .map((v) => [v.name, bn.format(toBn(v.value)), data.period]),
              ])
            }
          >
            Download CSV
          </button>
        )}
      </div>

      <p className="sub">{spec.blurb}</p>

      {/* Filters in one row above the chart. Two dimensions, both explicit —
          nothing here silently defaults a reader into the wrong basis. */}
      <div className="controls">
        <div className="segmented" role="group" aria-label="Measure">
          {(Object.keys(MEASURES) as Measure[]).map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={m === measure}
              onClick={() => setMeasure(m)}
            >
              {MEASURES[m].label}
            </button>
          ))}
        </div>
        <div className="segmented" role="group" aria-label="Budget or actual">
          {(Object.keys(BASES) as Basis[]).map((b) => (
            <button
              key={b}
              type="button"
              aria-pressed={b === basis}
              onClick={() => setBasis(b)}
            >
              {BASES[b]}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="state error" role="status">
          {error}
        </div>
      )}
      {!error && !data && <p className="state">Loading provincial figures…</p>}

      {data && option && (
        <>
          <figure className="panel">
            <figcaption>
              <h3>
                {spec.label} by province, {BASES[basis].toLowerCase()},{" "}
                {data.period}
              </h3>
              <p>
                {top && bottom && top.geo_code !== bottom.geo_code
                  ? `${top.name} ${spec.noun} the most — NPR ${bn.format(toBn(top.value))} bn, against NPR ${bn.format(toBn(bottom.value))} bn for ${bottom.name}.`
                  : `${spec.label} by province, NPR billion.`}
              </p>
            </figcaption>
            <EChart
              option={option}
              height={300}
              ariaLabel={`Horizontal bar chart comparing ${spec.label.toLowerCase()} (${BASES[basis].toLowerCase()}) across Nepal's seven provinces in ${data.period}, in NPR billion. ${sorted
                .slice()
                .reverse()
                .map((v) => `${v.name} ${bn.format(toBn(v.value))}`)
                .join("; ")}.`}
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
                  {spec.label} ({BASES[basis]}) by province, {data.period}, NPR billion
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Province</th>
                    <th scope="col">NPR billion</th>
                  </tr>
                </thead>
                <tbody>
                  {tableRows.map((r) => (
                    <tr key={r[0]}>
                      <th scope="row">{r[0]}</th>
                      <td>{r[1]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <p className="fiscal-provenance">
            <strong>Source:</strong> {data.provenance.source} —{" "}
            {data.provenance.dataset}, compiled from the Provincial Ministries of
            Finance and the Financial Comptroller General Office. Each province
            figure is the source&rsquo;s own published number; the provincial total
            is the sum of its categories, checked against the source&rsquo;s own
            all-provinces figure for every category and year. Cross-checked against
            two provinces&rsquo; own announced budgets for FY 2023/24 — Bagmati and
            Koshi both reconcile, the small residual being each province&rsquo;s
            financial-management line, which the source keeps in a separate sheet.
            Stored in NPR million as published; shown here in NPR billion. Licence:{" "}
            {data.provenance.license ?? "not stated"}.
          </p>
        </>
      )}
    </section>
  );
}
