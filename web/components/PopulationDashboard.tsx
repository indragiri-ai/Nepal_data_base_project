"use client";

// Population & census dashboard — Census 2021 painted on the map of Nepal.
//
// Pick an indicator, see every province / district / municipality at once, hover
// for exact figures, drill from a district into its local units, and take the
// data as CSV. Regions join by P-code; values come from our warehouse (raw-first
// from the NSO census), never live-scraped. Which levels exist comes from the
// data: a district-only indicator shows no (empty) municipality map (P2B.S8b).

import { useCallback, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import {
  ApiError,
  fetchGeoValues,
  fetchIndicators,
  type GeoDataResponse,
  type GeoLevel,
  type IndicatorSummary,
} from "@/lib/api";
import { formatValue } from "@/lib/format";
import { downloadCsv } from "@/lib/csv";

const ChoroplethMap = dynamic(() => import("@/components/ChoroplethMap"), {
  ssr: false,
  loading: () => <div className="state">Preparing map…</div>,
});

const LEVELS: Array<{ id: GeoLevel; label: string }> = [
  { id: "province", label: "By province" },
  { id: "district", label: "By district" },
  { id: "local_unit", label: "By municipality" },
];

const NOUN: Record<GeoLevel, string> = {
  province: "provinces",
  district: "districts",
  local_unit: "municipalities",
};
const NOUN_ONE: Record<GeoLevel, string> = {
  province: "province",
  district: "district",
  local_unit: "municipality",
};

// The picker held 7 census indicators until the bulk tables landed; it now holds
// 56, which is unusable as one flat list. Group by source census table, in the
// order a reader is likely to want. Anything unmatched falls into the headline
// group rather than disappearing — a newly loaded table must never go missing
// from the picker just because nobody added it here.
const INDICATOR_GROUPS: Array<{ label: string; prefix: string }> = [
  { label: "Literacy", prefix: "CENSUS_INDV17_" },
  { label: "Education level", prefix: "CENSUS_INDV18_" },
  { label: "Disability", prefix: "CENSUS_INDV16_" },
  { label: "Age and sex", prefix: "CENSUS_INDV04_" },
  { label: "Household facilities", prefix: "CENSUS_HHLD10_" },
  { label: "Cooking fuel", prefix: "CENSUS_HHLD07_" },
  { label: "Toilets", prefix: "CENSUS_HHLD09_" },
];

const HEADLINE_GROUP = "Headline indicators";

type IndicatorGroup = { label: string; items: IndicatorSummary[] };

export function groupIndicators(list: IndicatorSummary[]): IndicatorGroup[] {
  const groups = new Map<string, IndicatorSummary[]>();
  for (const ind of list) {
    const match = INDICATOR_GROUPS.find((g) => ind.code.startsWith(g.prefix));
    const label = match ? match.label : HEADLINE_GROUP;
    const items = groups.get(label);
    if (items) items.push(ind);
    else groups.set(label, [ind]);
  }
  return [HEADLINE_GROUP, ...INDICATOR_GROUPS.map((g) => g.label)]
    .filter((label) => groups.has(label))
    .map((label) => ({
      label,
      items: (groups.get(label) ?? []).slice().sort(tableTotalFirst),
    }));
}

// A table's own total is the map-worthy number, but the API returns codes
// alphabetically, which buries "…_ROWTOTAL" under its own categories.
function tableTotalFirst(a: IndicatorSummary, b: IndicatorSummary): number {
  const rank = (code: string) => (code.endsWith("_ROWTOTAL") ? 0 : 1);
  return rank(a.code) - rank(b.code) || a.name.localeCompare(b.name);
}

export default function PopulationDashboard() {
  const [indicators, setIndicators] = useState<IndicatorSummary[] | null>(null);
  const [indicatorsError, setIndicatorsError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string>("CENSUS_POP_TOTAL");
  const [level, setLevel] = useState<GeoLevel>("district");
  // When set, we're drilled into one district's local units.
  const [drill, setDrill] = useState<{ code: string; name: string } | null>(null);

  const [geo, setGeo] = useState<GeoDataResponse | null>(null);
  const [geoError, setGeoError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showTable, setShowTable] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);

  const effectiveLevel: GeoLevel = drill ? "local_unit" : level;
  const parent = drill?.code;

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
    setMapError(null);
    fetchGeoValues(selected, effectiveLevel, parent)
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
  }, [selected, effectiveLevel, parent]);

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
  const ranked = useMemo(() => [...(geo?.values ?? [])].sort((a, b) => b.value - a.value), [geo]);

  // Click a district (district view) to drill into its local units.
  const onRegionClick = useCallback(
    (code: string) => {
      if (drill || level !== "district") return;
      const region = regions.find((r) => r.code === code);
      if (region) {
        setShowTable(false);
        setDrill({ code, name: region.name });
      }
    },
    [drill, level, regions],
  );

  const chooseLevel = (id: GeoLevel) => {
    setDrill(null);
    setShowTable(false);
    setLevel(id);
  };

  // A municipality-level request that came back empty = this indicator has no
  // municipality data. Say so plainly rather than draw an empty map.
  const noMunicipalityData =
    !loading && geoError !== null && effectiveLevel === "local_unit";

  return (
    <main className="page narrow">
      <div className="page-head">
        <p className="crumb">
          <a href="/">Overview</a> / Population
        </p>
        <h1>Population &amp; census</h1>
        <p className="sub">
          The National Population and Housing Census 2021, on the map — province,
          district, and all 753 municipalities, with the exact figure a hover away.
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
            No census indicators are loaded yet. Run the census ingestion, then refresh.
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
                    {groupIndicators(indicators ?? []).map((group) => (
                      <optgroup key={group.label} label={group.label}>
                        {group.items.map((ind) => (
                          <option key={ind.code} value={ind.code}>
                            {ind.name}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </span>
              </label>

              <div className="segmented" role="group" aria-label="Geography level">
                {LEVELS.map((l) => (
                  <button
                    key={l.id}
                    type="button"
                    aria-pressed={!drill && level === l.id}
                    onClick={() => chooseLevel(l.id)}
                  >
                    {l.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Drill breadcrumb */}
            {drill && (
              <p className="crumb drill-crumb">
                <button type="button" className="linklike" onClick={() => setDrill(null)}>
                  ← All districts
                </button>
                <span> / Municipalities of {drill.name}</span>
              </p>
            )}

            {!drill && level === "district" && (
              <p className="stat-note">Tip: click a district to see its municipalities.</p>
            )}

            {noMunicipalityData ? (
              <div className="state">
                Municipality-level data isn&rsquo;t available for this indicator yet — it
                exists for <strong>Population (Census 2021)</strong>.{" "}
                {drill && (
                  <button type="button" className="linklike" onClick={() => setDrill(null)}>
                    Back to districts
                  </button>
                )}
              </div>
            ) : (
              <MapArea
                loading={loading}
                error={geoError ?? mapError}
                geo={geo}
                regions={regions}
                ranked={ranked}
                level={effectiveLevel}
                drill={drill}
                showTable={showTable}
                onToggleTable={() => setShowTable((v) => !v)}
                onMapError={onMapError}
                onRegionClick={onRegionClick}
              />
            )}
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
  drill,
  showTable,
  onToggleTable,
  onMapError,
  onRegionClick,
}: {
  loading: boolean;
  error: string | null;
  geo: GeoDataResponse | null;
  regions: Array<{ code: string; name: string; nameNe: string | null; value: number }>;
  ranked: GeoDataResponse["values"];
  level: GeoLevel;
  drill: { code: string; name: string } | null;
  showTable: boolean;
  onToggleTable: () => void;
  onMapError: (message: string) => void;
  onRegionClick: (code: string) => void;
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
        {geo && showTable && <GeoTable geo={geo} ranked={ranked} level={level} />}
      </div>
    );
  }

  if (!geo) return <div className="state">Select an indicator to begin.</div>;

  const highest = ranked[0];
  const lowest = ranked[ranked.length - 1];
  const scope = drill ? `in_${drill.code}` : `by_${level}`;

  const exportCsv = () =>
    downloadCsv(`${geo.indicator.code}_${scope}.csv`, [
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
            {geo.values.length} {NOUN[level]}
            {drill ? ` in ${drill.name}` : ""} · {geo.unit_name} · Census {geo.period}
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
        districtFilter={drill?.code}
        onRegionClick={onRegionClick}
      />
      <p className="stat-note">
        Drag to pan · scroll to zoom · hover any {NOUN_ONE[level]} for its exact figure.
      </p>

      {showTable && (
        <GeoTable geo={geo} ranked={ranked} level={level} onRowClick={onRegionClick} />
      )}

      <p className="attribution">
        Source:{" "}
        <a href="https://censusresults.nsonepal.gov.np" target="_blank" rel="noreferrer">
          {geo.provenance.source} — {geo.provenance.dataset}
        </a>
        <span>· final results as published</span>
        <span>· boundaries: OCHA COD-AB P-codes</span>
      </p>
    </>
  );
}

function GeoTable({
  geo,
  ranked,
  level,
  onRowClick,
}: {
  geo: GeoDataResponse;
  ranked: GeoDataResponse["values"];
  level: GeoLevel;
  onRowClick?: (code: string) => void;
}) {
  const head = level === "province" ? "Province" : level === "district" ? "District" : "Municipality";
  const drillable = level === "district" && !!onRowClick;
  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr>
            <th>#</th>
            <th>{head}</th>
            <th>नाम</th>
            <th>{geo.unit_name}</th>
          </tr>
        </thead>
        <tbody>
          {ranked.map((v, i) => (
            <tr key={v.geo_code}>
              <td>{i + 1}</td>
              <td style={{ textAlign: "left" }}>
                {drillable ? (
                  <button
                    type="button"
                    className="linklike"
                    onClick={() => onRowClick?.(v.geo_code)}
                    title={`See ${v.name}'s municipalities`}
                  >
                    {v.name}
                  </button>
                ) : (
                  v.name
                )}
              </td>
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
