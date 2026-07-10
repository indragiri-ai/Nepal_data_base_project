"use client";

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
import { formatValue } from "@/components/IndicatorChart";

// ECharts touches the DOM, so it must not render on the server.
const IndicatorChart = dynamic(() => import("@/components/IndicatorChart"), {
  ssr: false,
  loading: () => <div className="state">Preparing chart…</div>,
});

export default function HomePage() {
  const [indicators, setIndicators] = useState<IndicatorSummary[] | null>(null);
  const [indicatorsError, setIndicatorsError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string>("");

  const [series, setSeries] = useState<DataResponse | null>(null);
  const [seriesError, setSeriesError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showTable, setShowTable] = useState(false);

  // Load the indicator list once, default to GDP growth (the milestone series).
  useEffect(() => {
    fetchIndicators()
      .then((list) => {
        setIndicators(list);
        const def = list.find((i) => i.code === "GDP_GROWTH") ?? list[0];
        if (def) setSelected(def.code);
      })
      .catch((err) => setIndicatorsError(messageFor(err)));
  }, []);

  // Load the selected series whenever the selection changes.
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

  // Group indicators by topic for the dropdown's <optgroup>s.
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
    <main>
      <header className="site">
        <h1>Nepal Data Portal</h1>
        <p>
          Pick an indicator to see Nepal&rsquo;s story — with the source behind every
          number. Or explore the <a href="/banking">banking sector dashboard →</a>
        </p>
      </header>

      <section className="card">
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
  if (loading) {
    return <div className="state">Loading data…</div>;
  }

  // Error state per Master Prompt §3.6: say what happened, and offer the table
  // if we still have data in hand.
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

  if (!series) {
    return <div className="state">Select an indicator to begin.</div>;
  }

  if (series.observations.length === 0) {
    return (
      <div className="state">
        No data points are available for {series.indicator.name} yet.
      </div>
    );
  }

  return (
    <>
      <h2 className="chart-title">{series.indicator.name}</h2>
      <p className="chart-sub">
        {series.geography_name} · {series.unit_name}
      </p>

      <IndicatorChart data={series} />

      <div style={{ marginTop: 8 }}>
        <button className="linklike" onClick={onToggleTable} type="button">
          {showTable ? "Hide data table" : "View data behind this chart"}
        </button>
      </div>
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
      , release {provenance.latest_release_date}
      {provenance.license ? ` · License: ${provenance.license}` : ""}
    </p>
  );
}

function messageFor(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "An unexpected error occurred.";
}
