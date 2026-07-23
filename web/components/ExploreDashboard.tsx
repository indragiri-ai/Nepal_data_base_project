"use client";

// Indicator explorer — every annual series in the warehouse, one at a time,
// with its provenance, a data table, and a CSV download.

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import {
  ApiError,
  fetchIndicators,
  fetchSeries,
  topicLabel,
  type DataResponse,
  type IndicatorSummary,
} from "@/lib/api";
import { formatDelta, formatValue } from "@/lib/format";
import { downloadCsv } from "@/lib/csv";

const TrendChart = dynamic(() => import("@/components/TrendChart"), {
  ssr: false,
  loading: () => <div className="state">Preparing chart…</div>,
});

export default function ExploreDashboard() {
  const [indicators, setIndicators] = useState<IndicatorSummary[] | null>(null);
  const [indicatorsError, setIndicatorsError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string>("");

  const [series, setSeries] = useState<DataResponse | null>(null);
  const [seriesError, setSeriesError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showTable, setShowTable] = useState(false);

  useEffect(() => {
    fetchIndicators()
      .then((list) => {
        // Annual country-level series only; NRB monthlies live on /banking.
        const annual = list.filter((i) => !i.code.startsWith("NRB_"));
        setIndicators(annual);
        // Deep link: /explore?indicator=CODE (validated); else default.
        const param =
          typeof window !== "undefined"
            ? new URLSearchParams(window.location.search).get("indicator")
            : null;
        const wanted = param ? annual.find((i) => i.code === param) : undefined;
        const def = wanted ?? annual.find((i) => i.code === "GDP_GROWTH") ?? annual[0];
        if (def) setSelected(def.code);
      })
      .catch((err) => setIndicatorsError(messageFor(err)));
  }, []);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    setLoading(true);
    setSeriesError(null);
    setShowTable(false);
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

  const grouped = useMemo(() => {
    const map = new Map<string, IndicatorSummary[]>();
    for (const ind of indicators ?? []) {
      const list = map.get(ind.topic) ?? [];
      list.push(ind);
      map.set(ind.topic, list);
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [indicators]);

  return (
    <main className="page narrow">
      <div className="page-head">
        <p className="crumb">
          <a href="/">Overview</a> / Explore
        </p>
        <h1>Explore indicators</h1>
        <p className="sub">
          Six decades of annual series for Nepal — economy, people, health,
          education, environment — each with the source and release behind it.
        </p>
      </div>

      <section className="panel">
        {indicatorsError ? (
          <div className="state error">
            <span className="what">Couldn&rsquo;t load the indicator list.</span>
            <span>{indicatorsError}</span>
          </div>
        ) : (
          <>
            <div className="controls">
              <label className="field">
                Indicator
                <span className="select-wrap">
                  <select
                    value={selected}
                    onChange={(e) => setSelected(e.target.value)}
                    disabled={!indicators}
                    aria-label="Select an indicator"
                  >
                    {!indicators && <option>Loading indicators…</option>}
                    {grouped.map(([topic, list]) => (
                      <optgroup key={topic} label={topicLabel(topic)}>
                        {list.map((ind) => (
                          <option key={ind.code} value={ind.code}>
                            {ind.name}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </span>
              </label>
            </div>

            <ChartArea
              loading={loading}
              error={seriesError}
              series={series}
              showTable={showTable}
              onToggleTable={() => setShowTable((v) => !v)}
            />
          </>
        )}
      </section>
    </main>
  );
}

function ChartArea({
  loading,
  error,
  series,
  showTable,
  onToggleTable,
}: {
  loading: boolean;
  error: string | null;
  series: DataResponse | null;
  showTable: boolean;
  onToggleTable: () => void;
}) {
  if (loading) return <div className="state">Loading data…</div>;

  if (error) {
    return (
      <div className="state error">
        <span className="what">We couldn&rsquo;t draw this chart.</span>
        <span>{error}</span>
        {series && (
          <button className="linklike" onClick={onToggleTable} type="button">
            Show the data as a table instead
          </button>
        )}
        {series && showTable && <DataTable series={series} />}
      </div>
    );
  }

  if (!series) return <div className="state">Select an indicator to begin.</div>;

  if (series.observations.length === 0) {
    return (
      <div className="state">
        No data points are available for {series.indicator.name} yet.
      </div>
    );
  }

  const obs = series.observations;
  const latest = obs[obs.length - 1];
  const prev = obs.length > 1 ? obs[obs.length - 2] : null;

  const exportCsv = () =>
    downloadCsv(`${series.indicator.code}_nepal.csv`, [
      ["period", "value", "unit", "status", "release_date"],
      ...obs.map((o) => [
        o.period,
        String(o.value),
        series.unit_code,
        o.status,
        o.release_date,
      ]),
    ]);

  return (
    <>
      <div className="chart-head">
        <div className="titles">
          <h2>{series.indicator.name}</h2>
          <p className="sub">
            {series.geography_name} · {series.unit_name} · annual
          </p>
        </div>
        <div className="toolbar">
          <button className="btn ghost small" onClick={exportCsv} type="button">
            Download CSV
          </button>
          <button className="btn ghost small" onClick={onToggleTable} type="button">
            {showTable ? "Hide table" : "View table"}
          </button>
        </div>
      </div>

      <div className="summary-row">
        <div className="cell">
          <p className="k">Latest</p>
          <p className="v">
            {formatValue(latest.value, series.unit_code)}
            <span className="when">{latest.period}</span>
          </p>
        </div>
        {prev && (
          <div className="cell">
            <p className="k">Change vs {prev.period}</p>
            <p className="v">{formatDelta(latest.value, prev.value, series.unit_code)}</p>
          </div>
        )}
        <div className="cell">
          <p className="k">Coverage</p>
          <p className="v">
            {obs[0].period}–{latest.period}
            <span className="when">{obs.length} points</span>
          </p>
        </div>
      </div>

      <TrendChart data={series} />

      {showTable && <DataTable series={series} />}

      <Attribution series={series} />
    </>
  );
}

function DataTable({ series }: { series: DataResponse }) {
  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr>
            <th>Year</th>
            <th>{series.unit_name}</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {series.observations.map((o) => (
            <tr key={o.period}>
              <td>{o.period}</td>
              <td>{formatValue(o.value, series.unit_code)}</td>
              <td>{o.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Attribution({ series }: { series: DataResponse }) {
  const { provenance } = series;
  return (
    <p className="attribution">
      Source:{" "}
      <a href="https://data.worldbank.org" target="_blank" rel="noreferrer">
        {provenance.source} — {provenance.dataset}
      </a>
      <span>· release {provenance.latest_release_date}</span>
      {provenance.license && <span>· {provenance.license}</span>}
    </p>
  );
}

function messageFor(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "An unexpected error occurred.";
}
