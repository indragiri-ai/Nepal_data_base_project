"use client";

// The disasters page (DIS.S2): a map of individual events, a hazard filter, a
// year range, and the feed of what the map is showing.
//
// The counts on this page are of what has been LOADED and is being shown, never
// "how many disasters Nepal has had" — the server caps how many events one
// request may return, and dressing a window up as a total would be the most
// obvious way to mislead with this data.

import { useCallback, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import {
  ApiError,
  fetchHazards,
  fetchIncidents,
  type Hazard,
  type Incident,
  type IncidentsResponse,
} from "@/lib/api";
import IncidentFeed from "@/components/IncidentFeed";
import TimeRangeControl, { type YearRange } from "@/components/TimeRangeControl";

// The scatter/geo bundle is loaded only on this page — no other sector should
// pay for a chart form it never draws.
const IncidentMap = dynamic(() => import("@/components/IncidentMap"), {
  ssr: false,
  loading: () => <p className="state">Loading the map…</p>,
});

// BIPAD's record begins on 14 April 2011.
const FIRST_YEAR = 2011;

// "Nothing matched" is an answer, not a failure — the API says it with a 404.
// Provenance is blank here because there is no row to have come from anywhere.
const NO_MATCHES: IncidentsResponse = {
  provenance: { source: "", dataset: "", license: null, latest_release_date: "" },
  filters: {},
  total_matching: 0,
  total_shown: 0,
  truncated: false,
  incidents: [],
};

export default function DisasterPanel() {
  const thisYear = new Date().getFullYear();
  const [hazards, setHazards] = useState<Hazard[]>([]);
  const [result, setResult] = useState<IncidentsResponse | null>(null);
  const [hazard, setHazard] = useState<string | null>(null);
  const [range, setRange] = useState<YearRange>({ from: thisYear, to: thisYear });
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Incident | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchHazards()
      .then((rows) => {
        if (!cancelled) setHazards(rows);
      })
      .catch(() => {
        /* the map still works without a legend */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setResult(null);
    setError(null);
    fetchIncidents({
      start: `${range.from}-01-01`,
      end: `${range.to}-12-31`,
      hazard: hazard ?? undefined,
    })
      .then((response) => {
        if (!cancelled) setResult(response);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        // 404 here means "nothing matched", which is an answer, not a fault.
        if (e instanceof ApiError && e.status === 404) {
          setResult(NO_MATCHES);
        } else {
          setError(e instanceof ApiError ? e.message : "Could not load incidents.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [range.from, range.to, hazard]);

  const hazardColors = useMemo(
    () => new Map(hazards.map((h) => [h.code, h.color])),
    [hazards],
  );

  const onMapError = useCallback((message: string) => setError(message), []);

  const shown = result?.incidents ?? [];

  // Summed over the rows on the page — which is why the caption below says
  // "among those shown" whenever the server cut the answer short. A null count
  // adds nothing: the source published no figure, and treating that as a zero
  // would quietly shrink a death toll.
  const harm = useMemo(() => {
    let deaths = 0;
    let missing = 0;
    let families = 0;
    for (const incident of shown) {
      deaths += incident.deaths ?? 0;
      missing += incident.missing ?? 0;
      families += incident.affected_families ?? 0;
    }
    const parts: string[] = [];
    if (deaths > 0) parts.push(`${deaths.toLocaleString()} recorded deaths`);
    if (missing > 0) parts.push(`${missing.toLocaleString()} missing`);
    if (families > 0) parts.push(`${families.toLocaleString()} families affected`);
    return parts;
  }, [shown]);

  const hazardLabel = hazard
    ? ` of ${hazards.find((h) => h.code === hazard)?.name_en ?? hazard}`
    : "";
  const spanLabel =
    range.from === range.to ? `in ${range.from}` : `from ${range.from} to ${range.to}`;

  return (
    <section className="disaster-panel" aria-labelledby="disaster-map">
      <div className="band-head">
        <h2 id="disaster-map">Where disasters happened</h2>
      </div>

      <p className="sub">
        Every incident recorded by the National Disaster Risk Reduction and Management
        Authority, at the place its own report gives. Choose a hazard and a span of years.
      </p>

      <TimeRangeControl
        min={FIRST_YEAR}
        max={thisYear}
        value={range}
        onChange={setRange}
        presets={[
          { label: "This year", range: { from: thisYear, to: thisYear } },
          { label: "Last 3 years", range: { from: thisYear - 2, to: thisYear } },
          { label: "Since 2015", range: { from: 2015, to: thisYear } },
        ]}
      />

      <div className="hazard-filter" role="group" aria-label="Filter by hazard">
        <button
          type="button"
          className={`btn ghost small${hazard === null ? " active" : ""}`}
          aria-pressed={hazard === null}
          onClick={() => setHazard(null)}
        >
          All hazards
        </button>
        {hazards.slice(0, 10).map((h) => (
          <button
            key={h.code}
            type="button"
            className={`btn ghost small${hazard === h.code ? " active" : ""}`}
            aria-pressed={hazard === h.code}
            onClick={() => setHazard(hazard === h.code ? null : h.code)}
          >
            <span
              className="hazard-swatch"
              style={{ background: h.color ?? "#545d6e" }}
              aria-hidden="true"
            />
            {h.name_en}
          </button>
        ))}
      </div>

      {error && (
        <div className="state error" role="status">
          {error}
        </div>
      )}

      {result === null && !error && <p className="state">Loading incidents…</p>}

      {result !== null && (
        <>
          <p className="head-meta">
            {result.truncated ? (
              <>
                <strong>
                  {result.total_matching.toLocaleString()} incidents{hazardLabel} were
                  recorded {spanLabel}.
                </strong>{" "}
                The map and list below show the {shown.length.toLocaleString()} most
                recent of them — the newest ones only, so they are not spread evenly
                across {range.from === range.to ? "the year" : "those years"}. Choose a
                shorter span to see the rest.
              </>
            ) : (
              <>
                All {shown.length.toLocaleString()} incident
                {shown.length === 1 ? "" : "s"}
                {hazardLabel} recorded {spanLabel}.
              </>
            )}
            {harm.length > 0 && (
              <>
                {" "}
                {result.truncated ? "Among those shown" : "In total"}: {harm.join(" · ")}.
              </>
            )}{" "}
            These are recorded incidents, not a national total.
          </p>

          <IncidentMap
            incidents={shown}
            hazards={hazards.map((h) => ({ code: h.code, name: h.name_en, color: h.color }))}
            onError={onMapError}
            onSelect={setSelected}
          />

          {selected && (
            <div className="incident-selected" role="status">
              <strong>{selected.title}</strong>
              <span>
                {selected.incident_on} · {selected.hazard_name} · {selected.geo_name}
              </span>
              <button type="button" className="btn ghost small" onClick={() => setSelected(null)}>
                Clear
              </button>
            </div>
          )}

          <h3 className="feed-head">What happened</h3>
          <IncidentFeed
            incidents={shown}
            hazardColors={hazardColors}
            onSelect={setSelected}
          />
        </>
      )}
    </section>
  );
}
