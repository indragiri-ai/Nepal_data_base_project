"use client";

// Live headline figures on the landing page. Pure numbers — no chart JS is
// loaded on this route, which keeps the first page a visitor sees light.

import { useEffect, useState } from "react";
import { fetchIndicators, fetchSeries, type DataResponse } from "@/lib/api";
import { formatCompact, formatDelta, formatValue } from "@/lib/format";

interface Tile {
  label: string;
  value: string;
  unit?: string;
  sub: string;
  delta?: string;
}

/** Latest + previous observation of a series, preferring the aggregate
 *  breakdown when one exists (NRB series carry a bfi_class). */
function latestPair(data: DataResponse): { latest: number; prev: number | null; period: string } | null {
  const classes = new Set(data.observations.map((o) => o.breakdowns?.bfi_class ?? ""));
  const pick = classes.has("overall")
    ? "overall"
    : classes.has("commercial_banks")
      ? "commercial_banks"
      : null;
  const obs = data.observations.filter(
    (o) => pick === null || (o.breakdowns?.bfi_class ?? "") === pick,
  );
  if (obs.length === 0) return null;
  const last = obs[obs.length - 1];
  const prev = obs.length > 1 ? obs[obs.length - 2].value : null;
  return { latest: last.value, prev, period: last.period };
}

export default function HeroStats() {
  const [tiles, setTiles] = useState<Tile[] | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const spec = [
      { code: "GDP_GROWTH", label: "GDP growth", source: "World Bank" },
      { code: "CPI_YOY", label: "Inflation (CPI)", source: "World Bank" },
      { code: "POP_TOTAL", label: "Population", source: "World Bank" },
      { code: "NRB_BFS_LENDING_RATE", label: "Avg lending rate", source: "Nepal Rastra Bank" },
    ];

    Promise.allSettled([
      fetchIndicators(),
      ...spec.map((s) => fetchSeries(s.code, "NP")),
    ]).then((results) => {
      if (cancelled) return;
      const [indicators, ...seriesResults] = results;

      const built: Tile[] = [];
      seriesResults.forEach((r, i) => {
        if (r.status !== "fulfilled") return;
        const data = r.value as DataResponse;
        const pair = latestPair(data);
        if (!pair) return;
        const s = spec[i];
        const isCount = data.unit_code === "COUNT";
        built.push({
          label: s.label,
          value: isCount ? formatCompact(pair.latest) : formatValue(pair.latest, data.unit_code),
          sub: `${pair.period} · ${s.source}`,
          delta:
            pair.prev != null
              ? `${formatDelta(pair.latest, pair.prev, data.unit_code)} vs previous`
              : undefined,
        });
      });

      if (built.length === 0) {
        setFailed(true);
        return;
      }
      setTiles(built);

      if (indicators.status === "fulfilled") {
        setNote(
          `Live from the portal's own open API · ${indicators.value.length} indicators from official sources`,
        );
      }
    });

    return () => {
      cancelled = true;
    };
  }, []);

  if (failed) return null; // the page stands on its own if the API is unreachable

  return (
    <>
      <div className="stat-row">
        {(tiles ?? Array.from({ length: 4 })).map((tile, i) =>
          tile ? (
            <div className="stat-tile" key={(tile as Tile).label}>
              <p className="label">{(tile as Tile).label}</p>
              <p className="value">{(tile as Tile).value}</p>
              <p className="sub">
                {(tile as Tile).delta ? (
                  <>
                    <span className="delta">{(tile as Tile).delta}</span>
                    {" · "}
                  </>
                ) : null}
                {(tile as Tile).sub}
              </p>
            </div>
          ) : (
            <div className="stat-tile" key={i} aria-hidden="true">
              <p className="label skeleton">loading</p>
              <p className="value skeleton">00.0</p>
              <p className="sub skeleton">loading period</p>
            </div>
          ),
        )}
      </div>
      {note && <p className="stat-note">{note}</p>}
    </>
  );
}
