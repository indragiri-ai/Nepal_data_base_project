"use client";

// Population & census dashboard — Census 2021 painted on the map of Nepal.
//
// The thing the official PDF tables make hard: pick an indicator, see every
// province or district at once, hover for exact figures, and take the data
// with you as CSV. Regions join by P-code; values come from our warehouse
// (raw-first from the NSO census API), never live-scraped.

import { useCallback, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import {
  ApiError,
  fetchGeoValues,
  fetchIndicators,
  type GeoDataResponse,
  type IndicatorSummary,
} from "@/lib/api";
import { formatValue } from "@/lib/format";
import { downloadCsv } from "@/lib/csv";

const ChoroplethMap = dynamic(() => import("@/components/ChoroplethMap"), {
  ssr: false,
  loading: () => <div className="state">Preparing map…</div>,
});

type Level = "province" | "district";

const LEVELS: Array<{ id: Level; label: string }> = [
  { id: "province", label: "By province" },
  { id: "district", label: "By district" },
];

export default function PopulationDashboard() {
  const [indicators, setIndicators] = useState<IndicatorSummary[] | null>(null);
  const [indicatorsError, setIndicatorsError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string>("CENSUS_POP_TOTAL");
  const [level, setLevel] = useState<Level>("district");

  const [geo, setGeo] = useState<GeoDataResponse | null>(null);
  const [geoError, setGeoError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showTable, setShowTable] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);

  useEffect(() => {
    fetchIndicators()
      .then((list) => setIndicators(list.filter((i) => i.code.startsWith("CENSUS_"))))
      .catch((err) => setIndicatorsError(messageFor(err)));
  }, []);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    setLoading(true);
    setGeoError(null);
    fetchGeoValues(selected, level)
      .then((data) => {
        if (!cancelled) setGeo(data);
      })
      .catch((err) => {
        if (!cancelled) {
          setGeo(null);
          setGeoError(messageFor(err));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selected, level]);

  const onMapError = useCallback((message: string) => setMapError(message), []);

  const regions = useMemo(
    () =>
      (geo?.values ?? []).map((v) => ({
        code: v.geo_code,
        name: v.name,
        nameNe: v.name_ne,
        value: v.value,
      })),
    [geo],
  );

  const ranked = useMemo(
    () => [...(geo?.values ?? [])].sort((a, b) => b.value - a.value),
    [geo],
  );

  return (
    <main className="page narrow">
      <div className="page-head">
        <p className="crumb">
          <a href="/">Overview</a> / Population
        </p>
        <h1>Population &amp; census</h1>
        <p className="sub">
          The National Population and Housing Census 2021, on the map — every
          province and district, with the exact figure a hover away.
        </p>
      </div>

      <section className="panel">
        {indicatorsError ? (
          <div className="state error">
            <span className="what">Couldn&rsquo;t load the indicator list.</span>
            <span>{indicatorsError}</span>
          </div>
        ) : indicators !== null && indicators.length === 0 ? (
          <div className="state">
            No census indicators are loaded yet. Run the census ingestion, then
            refresh.
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
                    aria-label="Select a census indicator"
                  >
                    {!indicators && <option>Loading indicators…</option>}
                    {(indicators ?? []).map((ind) => (
                      <option key={ind.code} value={ind.code}>
                        {ind.name}
                      </option>
                    ))}
                  </select>
                </span>
              </label>

              <div className="segmented" role="group" aria-label="Geography level">
                {LEVELS.map((l) => (
                  <button
                    key={l.id}
                    type="button"
                    aria-pressed={level === l.id}
                    onClick={() => setLevel(l.id)}
                  >
                    {l.label}
                  </button>
                ))}
              </div>
            </div>

            <MapArea
              loading={loading}
              error={geoError ?? mapError}
              geo={geo}
              regions={regions}
              ranked={ranked}
              level={level}
              showTable={showTable}
              onToggleTable={() => setShowTable((v) => !v)}
              onMapError={onMapError}
            />
          </>
        )}
      </section>
    </main>
  );
}

function MapArea({
  loading,
  error,
  geo,
  regions,
  ranked,
  level,
  showTable,
  onToggleTable,
  onMapError,
}: {
  loading: boolean;
  error: string | null;
  geo: GeoDataResponse | null;
  regions: Array<{ code: string; name: string; nameNe: string | null; value: number }>;
  ranked: GeoDataResponse["values"];
  level: Level;
  showTable: boolean;
  onToggleTable: () => void;
  onMapError: (message: string) => void;
}) {
  if (loading) return <div className="state">Loading data…</div>;

  if (error) {
    return (
      <div className="state error">
        <span className="what">We couldn&rsquo;t draw the map.</span>
        <span>{error}</span>
        {geo && (
          <button className="linklike" onClick={onToggleTable} type="button">
            Show the data as a table instead
          </button>
        )}
        {geo && showTable && <GeoTable geo={geo} ranked={ranked} />}
      </div>
    );
  }

  if (!geo) return <div className="state">Select an indicator to begin.</div>;

  const highest = ranked[0];
  const lowest = ranked[ranked.length - 1];

  const exportCsv = () =>
    downloadCsv(`${geo.indicator.code}_by_${level}.csv`, [
      ["code", "name", "name_ne", geo.unit_code.toLowerCase(), "census_year"],
      ...geo.values.map((v) => [
        v.geo_code,
        v.name,
        v.name_ne ?? "",
        String(v.value),
        geo.period,
      ]),
    ]);

  return (
    <>
      <div className="chart-head">
        <div className="titles">
          <h2>{geo.indicator.name}</h2>
          <p className="sub">
            {geo.values.length} {level === "province" ? "provinces" : "districts"} ·{" "}
            {geo.unit_name} · Census {geo.period}
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

      {highest && lowest && (
        <div className="summary-row">
          <div className="cell">
            <p className="k">Highest</p>
            <p className="v">
              {formatValue(highest.value, geo.unit_code)}
              <span className="when">{highest.name}</span>
            </p>
          </div>
          <div className="cell">
            <p className="k">Lowest</p>
            <p className="v">
              {formatValue(lowest.value, geo.unit_code)}
              <span className="when">{lowest.name}</span>
            </p>
          </div>
        </div>
      )}

      <ChoroplethMap
        level={level}
        data={regions}
        unitCode={geo.unit_code}
        onError={onMapError}
      />
      <p className="stat-note">
        Drag to pan · scroll to zoom · hover any {level} for its exact figure.
      </p>

      {showTable && <GeoTable geo={geo} ranked={ranked} />}

      <p className="attribution">
        Source:{" "}
        <a href="https://censusresults.nsonepal.gov.np" target="_blank" rel="noreferrer">
          {geo.provenance.source} — {geo.provenance.dataset}
        </a>
        <span>· final results as published</span>
        <span>· boundaries: OCHA/Survey Dept. P-codes (MIT-licensed GeoJSON)</span>
      </p>
    </>
  );
}

function GeoTable({
  geo,
  ranked,
}: {
  geo: GeoDataResponse;
  ranked: GeoDataResponse["values"];
}) {
  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr>
            <th>#</th>
            <th>{geo.level === "province" ? "Province" : "District"}</th>
            <th>नाम</th>
            <th>{geo.unit_name}</th>
          </tr>
        </thead>
        <tbody>
          {ranked.map((v, i) => (
            <tr key={v.geo_code}>
              <td>{i + 1}</td>
              <td style={{ textAlign: "left" }}>{v.name}</td>
              <td style={{ textAlign: "left" }}>{v.name_ne ?? "—"}</td>
              <td>{formatValue(v.value, geo.unit_code)}</td>
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
