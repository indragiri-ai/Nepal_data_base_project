"use client";

// Banking sector dashboard — NRB Banking and Financial Statistics (Monthly).
//
// Every NRB_BFS_* indicator is a monthly time series broken down by BFI class
// (commercial banks / development banks / finance companies / overall). This
// page lets anyone follow any of them through time — the thing the monthly
// PDF/Excel files make hard — with month-over-month and year-over-year views.

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import {
  ApiError,
  fetchIndicators,
  fetchSeries,
  type DataResponse,
  type IndicatorSummary,
} from "@/lib/api";
import { formatValue } from "@/components/IndicatorChart";
import { CLASS_COLORS, type ClassSeries } from "@/components/BankingChart";

const BankingChart = dynamic(() => import("@/components/BankingChart"), {
  ssr: false,
  loading: () => <div className="state">Preparing chart…</div>,
});

// Dashboard sections, mirroring table C4 of the publication (and the
// `section` field in ingestion/nrb/bfs_layout.py — keep in sync by hand).
const SECTIONS: Array<{ label: string; codes: string[] }> = [
  {
    label: "Credit & deposit ratios",
    codes: [
      "NRB_BFS_DEPOSIT_TO_GDP", "NRB_BFS_CREDIT_TO_GDP", "NRB_BFS_CREDIT_TO_DEPOSIT",
      "NRB_BFS_CD_RATIO", "NRB_BFS_CCD_RATIO", "NRB_BFS_FIXED_DEPOSIT_SHARE",
      "NRB_BFS_SAVING_DEPOSIT_SHARE", "NRB_BFS_CURRENT_DEPOSIT_SHARE",
      "NRB_BFS_CALL_DEPOSIT_SHARE", "NRB_BFS_NPL_RATIO", "NRB_BFS_LLP_RATIO",
      "NRB_BFS_DEPRIVED_SECTOR_RATIO",
    ],
  },
  {
    label: "Liquidity ratios",
    codes: [
      "NRB_BFS_CASH_TO_DEPOSIT", "NRB_BFS_GOVSEC_TO_DEPOSIT",
      "NRB_BFS_LIQUID_ASSETS_TO_DEPOSIT",
    ],
  },
  {
    label: "Capital adequacy",
    codes: ["NRB_BFS_CORE_CAPITAL_RWA", "NRB_BFS_TOTAL_CAPITAL_RWA"],
  },
  {
    label: "Financial access",
    codes: [
      "NRB_BFS_INSTITUTIONS", "NRB_BFS_BRANCHES", "NRB_BFS_DEPOSIT_ACCOUNTS",
      "NRB_BFS_LOAN_ACCOUNTS", "NRB_BFS_BRANCHLESS_CENTERS", "NRB_BFS_BRANCHLESS_CUSTOMERS",
      "NRB_BFS_MOBILE_BANKING_USERS", "NRB_BFS_INTERNET_BANKING_USERS", "NRB_BFS_ATMS",
      "NRB_BFS_DEBIT_CARDS", "NRB_BFS_CREDIT_CARDS", "NRB_BFS_PREPAID_CARDS",
    ],
  },
  {
    label: "Interest rates (commercial banks)",
    codes: [
      "NRB_BFS_DEPOSIT_RATE", "NRB_BFS_DEPOSIT_RATE_SAVING", "NRB_BFS_DEPOSIT_RATE_FIXED",
      "NRB_BFS_DEPOSIT_RATE_CALL", "NRB_BFS_LENDING_RATE", "NRB_BFS_SPREAD_RATE",
    ],
  },
];

const CLASS_LABELS: Record<string, string> = {
  overall: "All BFIs (overall)",
  commercial_banks: "Commercial banks (A)",
  development_banks: "Development banks (B)",
  finance_companies: "Finance companies (C)",
};
const CLASS_ORDER = ["overall", "commercial_banks", "development_banks", "finance_companies"];

type ViewMode = "level" | "mom" | "yoy";

export default function BankingPage() {
  const [indicators, setIndicators] = useState<IndicatorSummary[] | null>(null);
  const [indicatorsError, setIndicatorsError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string>("NRB_BFS_NPL_RATIO");
  const [enabledClasses, setEnabledClasses] = useState<string[]>(CLASS_ORDER);
  const [mode, setMode] = useState<ViewMode>("level");

  const [series, setSeries] = useState<DataResponse | null>(null);
  const [seriesError, setSeriesError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showTable, setShowTable] = useState(false);

  useEffect(() => {
    fetchIndicators()
      .then((list) => setIndicators(list.filter((i) => i.code.startsWith("NRB_BFS_"))))
      .catch((err) => setIndicatorsError(messageFor(err)));
  }, []);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    setLoading(true);
    setSeriesError(null);
    fetchSeries(selected, "NP")
      .then((data) => {
        if (!cancelled) setSeries(data);
      })
      .catch((err) => {
        if (!cancelled) {
          setSeries(null);
          setSeriesError(messageFor(err));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selected]);

  const byName = useMemo(() => {
    const m = new Map<string, IndicatorSummary>();
    for (const i of indicators ?? []) m.set(i.code, i);
    return m;
  }, [indicators]);

  // Sections that actually have data in the API (hides e.g. nothing-loaded states).
  const sections = useMemo(
    () =>
      SECTIONS.map((s) => ({
        label: s.label,
        items: s.codes.map((c) => byName.get(c)).filter(Boolean) as IndicatorSummary[],
      })).filter((s) => s.items.length > 0),
    [byName],
  );

  const classSeries = useMemo(
    () => (series ? buildClassSeries(series, enabledClasses, mode) : []),
    [series, enabledClasses, mode],
  );

  const unitCode = mode === "level" ? (series?.unit_code ?? "") : "PCT";
  const unitName =
    mode === "level"
      ? (series?.unit_name ?? "")
      : mode === "mom"
        ? "% change vs previous month"
        : "% change vs same month last year";

  return (
    <main>
      <header className="site">
        <h1>Banking Sector Dashboard</h1>
        <p>
          Nepal&rsquo;s banking system, month by month — from Nepal Rastra Bank&rsquo;s
          Banking and Financial Statistics. <a href="/">← All indicators</a>
        </p>
      </header>

      <section className="card">
        {indicatorsError ? (
          <div className="state error">
            <span className="what">Couldn&rsquo;t load the indicator list.</span>
            <span>{indicatorsError}</span>
          </div>
        ) : indicators !== null && indicators.length === 0 ? (
          <div className="state">
            No banking indicators are loaded yet. Run the NRB ingestion
            (make nrb-bfs-acquire → extract → review → promote), then refresh.
          </div>
        ) : (
          <>
            <div className="controls">
              <label className="field">
                Indicator
                <select
                  value={selected}
                  onChange={(e) => setSelected(e.target.value)}
                  disabled={!indicators}
                  aria-label="Select a banking indicator"
                >
                  {!indicators && <option>Loading indicators…</option>}
                  {sections.map((s) => (
                    <optgroup key={s.label} label={s.label}>
                      {s.items.map((ind) => (
                        <option key={ind.code} value={ind.code}>
                          {ind.name}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </label>

              <label className="field">
                View
                <select
                  value={mode}
                  onChange={(e) => setMode(e.target.value as ViewMode)}
                  aria-label="Select the view mode"
                >
                  <option value="level">Levels</option>
                  <option value="mom">Month-over-month change (%)</option>
                  <option value="yoy">Year-over-year change (%)</option>
                </select>
              </label>
            </div>

            <fieldset className="class-picker">
              <legend>Bank classes</legend>
              {CLASS_ORDER.map((cls) => (
                <label key={cls} className="class-option">
                  <input
                    type="checkbox"
                    checked={enabledClasses.includes(cls)}
                    onChange={(e) =>
                      setEnabledClasses((prev) =>
                        e.target.checked
                          ? [...CLASS_ORDER.filter((c) => prev.includes(c) || c === cls)]
                          : prev.filter((c) => c !== cls),
                      )
                    }
                  />
                  <span style={{ color: CLASS_COLORS[cls] }}>■</span> {CLASS_LABELS[cls]}
                </label>
              ))}
            </fieldset>

            <ChartArea
              loading={loading}
              error={seriesError}
              series={series}
              classSeries={classSeries}
              unitCode={unitCode}
              unitName={unitName}
              showTable={showTable}
              onToggleTable={() => setShowTable((v) => !v)}
            />
          </>
        )}
      </section>
    </main>
  );
}

/** Pivot the flat observation list into one aligned series per BFI class,
 *  applying the level / MoM / YoY transformation. */
function buildClassSeries(
  data: DataResponse,
  enabledClasses: string[],
  mode: ViewMode,
): ClassSeries[] {
  // Periods in API order (already sorted by true Gregorian dates).
  const periods: string[] = [];
  const seen = new Set<string>();
  for (const o of data.observations) {
    if (!seen.has(o.period)) {
      seen.add(o.period);
      periods.push(o.period);
    }
  }
  const index = new Map(periods.map((p, i) => [p, i]));

  const result: ClassSeries[] = [];
  for (const cls of CLASS_ORDER) {
    if (!enabledClasses.includes(cls)) continue;
    const values: (number | null)[] = new Array(periods.length).fill(null);
    for (const o of data.observations) {
      if ((o.breakdowns?.bfi_class ?? "overall") === cls) {
        values[index.get(o.period)!] = o.value;
      }
    }
    if (values.every((v) => v === null)) continue; // class absent for this indicator

    let out = values;
    if (mode !== "level") {
      const lag = mode === "mom" ? 1 : 12;
      out = values.map((v, i) => {
        const prev = i >= lag ? values[i - lag] : null;
        if (v == null || prev == null || prev === 0) return null;
        return ((v - prev) / Math.abs(prev)) * 100;
      });
    }
    result.push({ bfiClass: cls, label: CLASS_LABELS[cls], periods, values: out });
  }
  return result;
}

function ChartArea({
  loading,
  error,
  series,
  classSeries,
  unitCode,
  unitName,
  showTable,
  onToggleTable,
}: {
  loading: boolean;
  error: string | null;
  series: DataResponse | null;
  classSeries: ClassSeries[];
  unitCode: string;
  unitName: string;
  showTable: boolean;
  onToggleTable: () => void;
}) {
  if (loading) return <div className="state">Loading data…</div>;

  if (error) {
    return (
      <div className="state error">
        <span className="what">We couldn&rsquo;t draw this chart.</span>
        <span>{error}</span>
      </div>
    );
  }

  if (!series) return <div className="state">Select an indicator to begin.</div>;

  if (classSeries.length === 0) {
    return (
      <div className="state">
        No data points to show — enable at least one bank class above.
      </div>
    );
  }

  return (
    <>
      <h2 className="chart-title">{series.indicator.name}</h2>
      <p className="chart-sub">
        {series.geography_name} · {unitName} · monthly, Nepali (BS) months
      </p>

      <BankingChart series={classSeries} unitCode={unitCode} unitName={unitName} />

      <div style={{ marginTop: 8 }}>
        <button className="linklike" onClick={onToggleTable} type="button">
          {showTable ? "Hide data table" : "View data behind this chart"}
        </button>
      </div>
      {showTable && <ClassTable classSeries={classSeries} unitCode={unitCode} />}

      <p className="attribution">
        Source:{" "}
        <a
          href="https://www.nrb.org.np/category/monthly-statistics/?department=bfr"
          target="_blank"
          rel="noreferrer"
        >
          {series.provenance.source} — {series.provenance.dataset}
        </a>
        , release {series.provenance.latest_release_date} · Provisional figures as
        published by NRB
      </p>
    </>
  );
}

function ClassTable({
  classSeries,
  unitCode,
}: {
  classSeries: ClassSeries[];
  unitCode: string;
}) {
  const periods = classSeries[0]?.periods ?? [];
  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr>
            <th>Month</th>
            {classSeries.map((s) => (
              <th key={s.bfiClass}>{s.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {periods.map((p, i) => (
            <tr key={p}>
              <td>{p}</td>
              {classSeries.map((s) => (
                <td key={s.bfiClass}>
                  {s.values[i] == null ? "—" : formatValue(s.values[i]!, unitCode)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function messageFor(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "An unexpected error occurred.";
}
