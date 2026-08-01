"use client";

// Public finance panel (WBF.S3) — Nepal's federal fiscal position.
//
// Charts follow the portal's dataviz method:
//  * Form first. Every series here is change-over-time, so every chart is a
//    line. No dual axis anywhere — all figures share one unit (NPR), so one
//    y-scale is honest; where a measure has a different magnitude (debt stock)
//    it gets its own chart rather than a second axis.
//  * Colour by entity, in the validated categorical order, never cycled:
//    revenue = series-1, expenditure = series-2. Budget-vs-actual is the SAME
//    entity measured two ways, so it reuses the entity's hue and separates by
//    dash pattern — a secondary encoding, not a new hue.
//  * >=2 series always carry a legend; the single-series chart carries none
//    (its title names it). The data table below is the accessible equivalent.
//
// Figures are stored in NPR million and displayed in NPR billion (an exact
// /1000), labelled as such everywhere, because Nepal's fiscal aggregates read
// naturally in billions.

import { useEffect, useMemo, useState } from "react";
import EChart, { CHART_INK, TOOLTIP_STYLE, type ChartOption } from "@/components/EChart";
import { ApiError, fetchSeries, type DataResponse } from "@/lib/api";
import { downloadCsv } from "@/lib/csv";

// The portal's validated categorical palette (globals.css). Order is the
// colourblind-safety mechanism — assign by entity, never re-order.
// One hue per ENTITY, held constant across every chart in the panel. Within a
// chart, budget-vs-actual is the same entity measured twice, so it reuses the
// entity's hue and separates by dash. No chart carries more than two series,
// so no hue is ever cycled.
const REVENUE = "#008300"; // --series-1
const EXPENDITURE = "#2a78d6"; // --series-2
const FINANCING = "#c98500"; // --series-3
const DEBT = "#4a3aa7"; // --series-4
const BALANCE = "#bb2340"; // --series-single (brand crimson)

const CODES = [
  "FISCAL_REVENUE_ACTUAL",
  "FISCAL_REVENUE_BUDGET",
  "FISCAL_EXPENDITURE_ACTUAL",
  "FISCAL_EXPENDITURE_BUDGET",
  "FISCAL_FINANCING_ACTUAL",
  "FISCAL_FINANCING_BUDGET",
  "FISCAL_NET_OPERATING_BALANCE_ACTUAL",
  "FISCAL_NET_OPERATING_BALANCE_BUDGET",
  "FISCAL_DEBT_STOCK",
] as const;

type Code = (typeof CODES)[number];
type SeriesMap = Partial<Record<Code, DataResponse>>;

/** NPR million -> NPR billion, the display unit. Exact, not rounded away. */
const toBn = (millions: number) => millions / 1000;

const bn = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });
const fmtBn = (v: number | null) => (v == null ? "—" : `${bn.format(v)}`);

/** `includeZero` anchors the axis to zero. Financing and the operating balance
 *  go negative, and an axis that floats free of zero makes a wholly negative
 *  series look like an ordinary rise and fall — the reader loses the sign. */
function baseOption(periods: string[], includeZero = false): ChartOption {
  return {
    // Generous right padding: the final category label (FY 2023/24) is wide and
    // was clipping against the plot edge.
    grid: { left: 8, right: 48, top: 40, bottom: 8, containLabel: true },
    tooltip: {
      ...TOOLTIP_STYLE,
      trigger: "axis",
      axisPointer: {
        type: "line",
        lineStyle: { color: CHART_INK.axisLine, type: "dashed", width: 1 },
      },
      valueFormatter: (v) => (v == null ? "—" : `NPR ${bn.format(v as number)} bn`),
    },
    xAxis: {
      type: "category",
      data: periods,
      boundaryGap: false,
      axisLabel: { color: CHART_INK.axisLabel, fontSize: 11, hideOverlap: true },
      axisLine: { lineStyle: { color: CHART_INK.axisLine } },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      scale: !includeZero,
      name: "NPR billion",
      nameTextStyle: { color: CHART_INK.axisLabel, fontSize: 11, align: "left" },
      nameGap: 12,
      axisLabel: {
        color: CHART_INK.axisLabel,
        fontSize: 11,
        formatter: (v: number) => bn.format(v),
      },
      splitLine: { lineStyle: { color: CHART_INK.grid } },
    },
  };
}

function line(
  name: string,
  values: (number | null)[],
  color: string,
  dashed = false,
) {
  return {
    name,
    type: "line" as const,
    data: values,
    smooth: 0.15,
    showSymbol: true,
    symbolSize: 8,
    connectNulls: false,
    lineStyle: { width: 2, color, type: dashed ? ("dashed" as const) : ("solid" as const) },
    itemStyle: { color },
    emphasis: { focus: "series" as const },
  };
}

// icon "line" (not roundRect) so the legend swatch REPRODUCES each series'
// dash pattern. Budget-vs-actual share one hue and are told apart by dashing;
// a solid roundRect swatch would render both entries identically and put the
// reader back on colour alone.
const LEGEND = {
  top: 0,
  left: 0,
  icon: "line",
  itemWidth: 22,
  itemHeight: 10,
  itemGap: 20,
  textStyle: { color: CHART_INK.secondary, fontSize: 12 },
};

function Tile({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="fiscal-tile">
      <span className="tile-label">{label}</span>
      <strong className="tile-value">{value}</strong>
      <span className="tile-note">{note}</span>
    </div>
  );
}

export default function FiscalPanel() {
  const [data, setData] = useState<SeriesMap | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showTable, setShowTable] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all(CODES.map((c) => fetchSeries(c, "NP").then((d) => [c, d] as const)))
      .then((pairs) => {
        if (!cancelled) setData(Object.fromEntries(pairs) as SeriesMap);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(
            e instanceof ApiError ? e.message : "Could not load the public finance data.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const view = useMemo(() => {
    if (!data?.FISCAL_REVENUE_ACTUAL) return null;
    const periods = data.FISCAL_REVENUE_ACTUAL.observations.map((o) => o.period);
    const seriesFor = (code: Code): (number | null)[] => {
      const obs = data[code]?.observations ?? [];
      const byPeriod = new Map(obs.map((o) => [o.period, toBn(o.value)]));
      return periods.map((p) => byPeriod.get(p) ?? null);
    };
    return {
      periods,
      revenue: seriesFor("FISCAL_REVENUE_ACTUAL"),
      revenueBudget: seriesFor("FISCAL_REVENUE_BUDGET"),
      expenditure: seriesFor("FISCAL_EXPENDITURE_ACTUAL"),
      expenditureBudget: seriesFor("FISCAL_EXPENDITURE_BUDGET"),
      financing: seriesFor("FISCAL_FINANCING_ACTUAL"),
      financingBudget: seriesFor("FISCAL_FINANCING_BUDGET"),
      balance: seriesFor("FISCAL_NET_OPERATING_BALANCE_ACTUAL"),
      balanceBudget: seriesFor("FISCAL_NET_OPERATING_BALANCE_BUDGET"),
      debt: seriesFor("FISCAL_DEBT_STOCK"),
      provenance: data.FISCAL_REVENUE_ACTUAL.provenance,
    };
  }, [data]);

  if (error) {
    return (
      <section className="fiscal-panel" aria-labelledby="fiscal">
        <h2 id="fiscal">Public finance</h2>
        <p className="state error" role="alert">
          {error}
        </p>
      </section>
    );
  }
  if (!view) {
    return (
      <section className="fiscal-panel" aria-labelledby="fiscal">
        <h2 id="fiscal">Public finance</h2>
        <p className="state">Loading Nepal&rsquo;s federal fiscal position…</p>
      </section>
    );
  }

  const last = view.periods.length - 1;
  const rev = view.revenue[last];
  const exp = view.expenditure[last];
  const revBud = view.revenueBudget[last];
  const debt = view.debt[last];
  const latestPeriod = view.periods[last];
  const expBud = view.expenditureBudget[last];
  const deficit = rev != null && exp != null ? exp - rev : null;
  const shortfall = rev != null && revBud != null ? revBud - rev : null;
  const expShortfall = exp != null && expBud != null ? expBud - exp : null;

  const revExpOption: ChartOption = {
    ...baseOption(view.periods),
    legend: { ...LEGEND, data: ["Revenue and grants", "Expenditure"] },
    series: [
      line("Revenue and grants", view.revenue, REVENUE),
      line("Expenditure", view.expenditure, EXPENDITURE),
    ],
  };

  const revenueBudgetOption: ChartOption = {
    ...baseOption(view.periods),
    legend: { ...LEGEND, data: ["Revenue collected", "Revenue budgeted"] },
    series: [
      line("Revenue collected", view.revenue, REVENUE),
      line("Revenue budgeted", view.revenueBudget, REVENUE, true),
    ],
  };

  const expenditureBudgetOption: ChartOption = {
    ...baseOption(view.periods),
    legend: { ...LEGEND, data: ["Expenditure spent", "Expenditure budgeted"] },
    series: [
      line("Expenditure spent", view.expenditure, EXPENDITURE),
      line("Expenditure budgeted", view.expenditureBudget, EXPENDITURE, true),
    ],
  };

  // Zero-anchored: this series is negative throughout.
  const financingOption: ChartOption = {
    ...baseOption(view.periods, true),
    legend: { ...LEGEND, data: ["Financing (actual)", "Financing (budget)"] },
    series: [
      line("Financing (actual)", view.financing, FINANCING),
      line("Financing (budget)", view.financingBudget, FINANCING, true),
    ],
  };

  // Zero-anchored: the sign is the whole point — above zero means day-to-day
  // running costs were covered by revenue, below zero means they were not.
  const balanceOption: ChartOption = {
    ...baseOption(view.periods, true),
    legend: { ...LEGEND, data: ["Balance (actual)", "Balance (budget)"] },
    series: [
      line("Balance (actual)", view.balance, BALANCE),
      line("Balance (budget)", view.balanceBudget, BALANCE, true),
    ],
  };

  const debtOption: ChartOption = {
    ...baseOption(view.periods),
    series: [line("Federal debt stock", view.debt, DEBT)],
  };

  const tableRows = view.periods.map((p, i) => [
    p,
    fmtBn(view.revenue[i]),
    fmtBn(view.revenueBudget[i]),
    fmtBn(view.expenditure[i]),
    fmtBn(view.expenditureBudget[i]),
    fmtBn(view.balance[i]),
    fmtBn(view.balanceBudget[i]),
    fmtBn(view.financing[i]),
    fmtBn(view.financingBudget[i]),
    fmtBn(view.debt[i]),
  ]);
  const header = [
    "Fiscal year",
    "Revenue (actual)",
    "Revenue (budget)",
    "Expenditure (actual)",
    "Expenditure (budget)",
    "Operating balance (actual)",
    "Operating balance (budget)",
    "Financing (actual)",
    "Financing (budget)",
    "Debt stock",
  ];

  return (
    <section className="fiscal-panel" aria-labelledby="fiscal">
      <div className="band-head">
        <h2 id="fiscal">Public finance</h2>
        <button
          type="button"
          className="btn ghost small"
          onClick={() =>
            downloadCsv("nepal-federal-fiscal.csv", [
              [...header.map((h) => `${h} (NPR billion)`)],
              ...tableRows,
            ])
          }
        >
          Download CSV
        </button>
      </div>
      <p className="fiscal-intro">
        Nepal&rsquo;s federal government accounts, {view.periods[0]}–{latestPeriod}. All
        figures in NPR billion.
      </p>

      <div className="fiscal-tiles">
        <Tile
          label="Revenue and grants"
          value={`NPR ${fmtBn(rev)} bn`}
          note={`collected, ${latestPeriod}`}
        />
        <Tile
          label="Expenditure"
          value={`NPR ${fmtBn(exp)} bn`}
          note={`spent, ${latestPeriod}`}
        />
        <Tile
          label="Spending above revenue"
          value={deficit == null ? "—" : `NPR ${fmtBn(deficit)} bn`}
          note={`${latestPeriod}`}
        />
        <Tile
          label="Debt stock"
          value={`NPR ${fmtBn(debt)} bn`}
          note={`outstanding, ${latestPeriod}`}
        />
      </div>

      <div className="fiscal-charts">
        <figure className="panel">
          <figcaption>
            <h3>Revenue and expenditure</h3>
            <p>
              Spending has exceeded revenue in every year shown — the gap is what
              borrowing has to cover.
            </p>
          </figcaption>
          <EChart
            option={revExpOption}
            height={320}
            ariaLabel={`Line chart of Nepal's federal revenue and grants against expenditure, ${view.periods[0]} to ${latestPeriod}, NPR billion. The same figures are in the table below.`}
          />
        </figure>

        <figure className="panel">
          <figcaption>
            <h3>Net operating balance</h3>
            <p>
              Revenue against day-to-day running costs. Above zero means routine
              spending was covered by revenue; below zero means it was not.
            </p>
          </figcaption>
          <EChart
            option={balanceOption}
            height={320}
            ariaLabel={`Line chart of Nepal's federal net operating balance, actual (solid) against budget (dashed), ${view.periods[0]} to ${latestPeriod}, NPR billion, axis anchored at zero.`}
          />
        </figure>

        <figure className="panel">
          <figcaption>
            <h3>Budgeted revenue against what was collected</h3>
            <p>
              {shortfall != null && shortfall > 0
                ? `In ${latestPeriod} the government budgeted NPR ${fmtBn(revBud)} bn and collected NPR ${fmtBn(rev)} bn — NPR ${fmtBn(shortfall)} bn less than planned.`
                : "Budgeted revenue against revenue actually collected."}
            </p>
          </figcaption>
          <EChart
            option={revenueBudgetOption}
            height={320}
            ariaLabel={`Line chart comparing budgeted federal revenue (dashed) with revenue actually collected (solid), ${view.periods[0]} to ${latestPeriod}, NPR billion.`}
          />
        </figure>

        <figure className="panel">
          <figcaption>
            <h3>Budgeted spending against what was spent</h3>
            <p>
              {expShortfall != null && expShortfall > 0
                ? `In ${latestPeriod} the government budgeted NPR ${fmtBn(expBud)} bn and spent NPR ${fmtBn(exp)} bn — NPR ${fmtBn(expShortfall)} bn of the budget went unspent.`
                : "Budgeted expenditure against expenditure actually incurred."}
            </p>
          </figcaption>
          <EChart
            option={expenditureBudgetOption}
            height={320}
            ariaLabel={`Line chart comparing budgeted federal expenditure (dashed) with expenditure actually incurred (solid), ${view.periods[0]} to ${latestPeriod}, NPR billion.`}
          />
        </figure>

        <figure className="panel">
          <figcaption>
            <h3>Financing</h3>
            <p>
              How the gap is covered — net borrowing and changes in the
              government&rsquo;s financial assets. Negative throughout, meaning a
              financing requirement in every year shown.
            </p>
          </figcaption>
          <EChart
            option={financingOption}
            height={320}
            ariaLabel={`Line chart of Nepal's federal financing, actual (solid) against budget (dashed), ${view.periods[0]} to ${latestPeriod}, NPR billion, axis anchored at zero.`}
          />
        </figure>

        <figure className="panel">
          <figcaption>
            <h3>Federal debt stock</h3>
            <p>Outstanding federal government debt at each year end.</p>
          </figcaption>
          <EChart
            option={debtOption}
            height={320}
            ariaLabel={`Line chart of Nepal's outstanding federal debt stock, ${view.periods[0]} to ${latestPeriod}, NPR billion.`}
          />
        </figure>
      </div>

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
              Nepal federal fiscal accounts, NPR billion
            </caption>
            <thead>
              <tr>
                {header.map((h) => (
                  <th key={h} scope="col">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tableRows.map((r) => (
                <tr key={r[0]}>
                  <th scope="row">{r[0]}</th>
                  {r.slice(1).map((c, i) => (
                    <td key={i}>{c}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="fiscal-provenance">
        <strong>Source:</strong> {view.provenance.source} — {view.provenance.dataset},
        compiled from Nepal&rsquo;s Ministry of Finance, the Provincial Ministries of
        Finance, the Financial Comptroller General Office and Nepal Rastra Bank.
        Verified against the FCGO Consolidated Financial Statements for FY 2018/19 and
        FY 2022/23 (within 0.4% on revenue). Stored in NPR million as published;
        shown here in NPR billion. Licence: {view.provenance.license ?? "not stated"}.
        Revenue category breakdowns are not published here — the source&rsquo;s
        components do not reconcile to its own total, and the reason is under query
        with the World Bank.
      </p>
    </section>
  );
}
