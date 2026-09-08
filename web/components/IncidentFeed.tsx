"use client";

// A dated list of individual disasters (DIS.S2).
//
// The portal's first event feed. Everything else here is a chart of a series;
// this is a list of things that happened, in the order they happened, which is
// how a person reads a record of events rather than a trend.
//
// Restraint is deliberate. These rows are deaths. No colour-coded severity
// badges, no counters that tick up, no ranking by "worst" — just what was
// recorded, where, and when, in the order it occurred.

import type { Incident } from "@/lib/api";

/** Only the counts the source actually published. A null means it published no
 *  figure and a zero means it counted none; showing "0 dead" where the source
 *  said nothing would put a number in the government's mouth. */
function harmOf(incident: Incident): { label: string; value: number }[] {
  const parts: { label: string; value: number }[] = [];
  if (incident.deaths) parts.push({ label: incident.deaths === 1 ? "death" : "deaths", value: incident.deaths });
  if (incident.missing) parts.push({ label: "missing", value: incident.missing });
  if (incident.injured) parts.push({ label: "injured", value: incident.injured });
  if (incident.affected_families)
    parts.push({
      label: incident.affected_families === 1 ? "family affected" : "families affected",
      value: incident.affected_families,
    });
  if (incident.houses_destroyed)
    parts.push({
      label: incident.houses_destroyed === 1 ? "home destroyed" : "homes destroyed",
      value: incident.houses_destroyed,
    });
  return parts;
}

function formatDate(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export default function IncidentFeed({
  incidents,
  hazardColors,
  limit = 60,
  onSelect,
}: {
  incidents: Incident[];
  hazardColors: Map<string, string | null>;
  limit?: number;
  onSelect?: (incident: Incident) => void;
}) {
  const shown = incidents.slice(0, limit);
  if (shown.length === 0) {
    return <p className="state">No incidents match these filters.</p>;
  }
  return (
    <div className="incident-feed">
      <ol className="incident-list">
        {shown.map((incident) => {
          const harm = harmOf(incident);
          return (
            <li key={incident.id} className="incident-row">
              <button
                type="button"
                className="incident-row-button"
                onClick={() => onSelect?.(incident)}
                aria-label={`${incident.title}, ${formatDate(incident.incident_on)}`}
              >
                <span
                  className="incident-dot"
                  style={{ background: hazardColors.get(incident.hazard) ?? "#545d6e" }}
                  aria-hidden="true"
                />
                <span className="incident-body">
                  <span className="incident-title">{incident.title}</span>
                  <span className="incident-meta">
                    {formatDate(incident.incident_on)} · {incident.hazard_name} ·{" "}
                    {incident.geo_name}
                    {!incident.verified && (
                      <span className="incident-unverified"> · unverified</span>
                    )}
                  </span>
                  {harm.length > 0 && (
                    <span className="incident-harm">
                      {harm.map((part) => (
                        <span key={part.label}>
                          <strong>{part.value.toLocaleString()}</strong> {part.label}
                        </span>
                      ))}
                    </span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
      {incidents.length > shown.length && (
        <p className="incident-more">
          Showing the {shown.length.toLocaleString()} most recent of{" "}
          {incidents.length.toLocaleString()} loaded. Narrow the dates to see further back.
        </p>
      )}
    </div>
  );
}
