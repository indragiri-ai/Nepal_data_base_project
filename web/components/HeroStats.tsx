"use client";

// Live headline figures on the landing page. Pure numbers — no chart JS is
// loaded on this route, which keeps the first page a visitor sees light.

import { useEffect, useState } from "react";
import { fetchIndicators, fetchSeries, type DataResponse } from "@/lib/api";
import { formatCompact, formatDelta, formatValue } from "@/lib/format";
import { latestPair } from "@/lib/latest";

interface Tile {
  label: string;
  value: string;
  unit?: string;
  sub: string;
  delta?: string;
}

export default function HeroStats() {
  const [tiles, setTiles] = useState<Tile[] | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;

    // Deliberately NOT the orbit's signature metrics (GDP growth, lending rate,
    // population, life expectancy…) — these complement the orbit instead of
    // repeating it, and avoid showing two different "populations" on one screen.
    const spec = [
      { code: "CPI_YOY", label: "Inflation (CPI)", source: "World Bank" },
      { code: "GDP_PCAP_USD", label: "GDP per capita", source: "World Bank" },
      { code: "REMITTANCES_GDP", label: "Remittances (% of GDP)", source: "World Bank" },
      { code: "INTERNET_USERS", label: "Internet users", source: "World Bank" },
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
        const value = isCount
          ? formatCompact(pair.latest)
          : data.unit_code === "PCT"
            ? `${pair.latest.toFixed(1)}%` // one decimal — no false precision
            : formatValue(pair.latest, data.unit_code);
        built.push({
          label: s.label,
          value,
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
