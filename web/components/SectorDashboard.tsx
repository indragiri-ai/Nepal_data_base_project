"use client";

// A sector page, dashboard-style (P2B.S5 / decision 0003): curated headline
// charts on top, the full searchable indicator list below, a source badge on
// everything. Reads its shape from lib/sectors.ts.

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import {
  fetchIndicators,
  fetchIndicatorSparks,
  ApiError,
  type IndicatorSummary,
  type IndicatorSpark,
} from "@/lib/api";
import {
  SECTORS,
  indicatorsForSector,
  sourceForIndicator,
  assignmentWarnings,
  type SectorDef,
} from "@/lib/sectors";
import HeadlineChart from "@/components/HeadlineChart";
import SparkCard from "@/components/SparkCard";

// Loaded on demand: FiscalPanel pulls in ECharts, and a static import put the
// whole charting bundle on EVERY sector page (5.7 kB -> 183 kB). Only Economy
// renders it, so only Economy should pay for it.
const FiscalPanel = dynamic(() => import("@/components/FiscalPanel"), {
  ssr: false,
  loading: () => <p className="state">Loading public finance…</p>,
});

const SOURCE_ORDER = ["World Bank", "Nepal Rastra Bank", "National Statistics Office"];

export default function SectorDashboard({ slug }: { slug: string }) {
  const sector = SECTORS.find((s) => s.slug === slug) as SectorDef;
  const [indicators, setIndicators] = useState<IndicatorSummary[] | null>(null);
  const [sparks, setSparks] = useState<Map<string, IndicatorSpark>>(new Map());
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  // Big sectors (Economy ~600) are capped per source group so the page stays
  // tight; a group expands on demand.
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const GROUP_CAP = 24;

  useEffect(() => {
    let cancelled = false;
    fetchIndicators()
      .then((all) => {
        if (cancelled) return;
        setIndicators(all);
        if (process.env.NODE_ENV !== "production") {
          const w = assignmentWarnings(all);
          if (w.length) console.warn("[sectors] assignment issues:", w);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof ApiError ? e.message : "Could not load indicators.");
      });
    // Sparklines load in parallel; if they fail the cards still render (value-less),
    // so a spark outage never blocks the page.
    fetchIndicatorSparks()
      .then((rows) => {
        if (!cancelled) setSparks(new Map(rows.map((r) => [r.code, r])));
      })
      .catch(() => {
        /* cards fall back to name + source badge */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const owned = useMemo(
    () => (indicators ? indicatorsForSector(sector, indicators) : []),
    [indicators, sector],
  );

  const sources = useMemo(() => {
    const set = new Set(owned.map((i) => sourceForIndicator(i)));
    return SOURCE_ORDER.filter((s) => set.has(s));
  }, [owned]);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return owned;
    return owned.filter(
      (i) => i.name.toLowerCase().includes(q) || i.code.toLowerCase().includes(q),
    );
  }, [owned, filter]);

  const grouped = useMemo(() => {
    return SOURCE_ORDER.map((src) => ({
      source: src,
      rows: filtered.filter((i) => sourceForIndicator(i) === src),
    })).filter((g) => g.rows.length > 0);
  }, [filtered]);

  const hasHeadlines = sector.headlineCodes.length > 0 || Boolean(sector.mapCard);

  return (
    <main className="page">
      <div className="page-head">
        <p className="crumb">
          <Link href="/">Overview</Link> / {sector.title}
        </p>
        <h1>{sector.title}</h1>
        <p className="sub">{sector.description}</p>
        {indicators && (
          <p className="head-meta">
            {owned.length} indicator{owned.length === 1 ? "" : "s"}
            {sources.length > 0 && <> · sources: {sources.join(", ")}</>}
          </p>
        )}
      </div>

      {error && (
        <div className="state error" role="status">
          {error} You can still browse other sectors from the menu.
        </div>
      )}

      {/* Headline band */}
      {hasHeadlines && (
        <section aria-labelledby="glance">
          <div className="band-head">
            <h2 id="glance">At a glance</h2>
            {sector.external && (
              <Link href={sector.external.href} className="btn ghost small">
                {sector.external.label}
              </Link>
            )}
          </div>
          <div className="headline-grid">
            {sector.headlineCodes.map((code) => (
              <div className="panel" key={code}>
                <HeadlineChart code={code} />
              </div>
            ))}
            {sector.mapCard && (
              <Link href={sector.mapCard.href} className="sector-card map-card">
                <h3>{sector.mapCard.label}</h3>
                <p>{sector.mapCard.note}</p>
                <span className="go">Open the map →</span>
              </Link>
            )}
          </div>
        </section>
      )}

      {/* Public finance (WBF.S3). Sits above the long indicator list because a
          676-item list is where fiscal data goes to be never found. */}
      {sector.slug === "economy" && <FiscalPanel />}

      {/* Full list */}
      <section aria-labelledby="all-list">
        <div className="band-head">
          <h2 id="all-list">All {sector.title} indicators</h2>
        </div>

        {owned.length === 0 && indicators && (
          <div className="state">No indicators are loaded for this sector yet.</div>
        )}

        {owned.length > 0 && (
          <>
            <div className="controls">
              <input
                type="text"
                className="filter-field"
                placeholder="Filter indicators…"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                aria-label={`Filter ${sector.title} indicators`}
              />
            </div>

            {grouped.length === 0 && (
              <div className="state">No indicators match “{filter}”.</div>
            )}

            {grouped.map((g) => {
              const isExpanded = expanded.has(g.source);
              const shown = isExpanded ? g.rows : g.rows.slice(0, GROUP_CAP);
              return (
                <div className="ind-group" key={g.source}>
                  <h3 className="ind-group-head">
                    {g.source} <span className="ind-group-count">{g.rows.length}</span>
                  </h3>
                  <div className="card-grid">
                    {shown.map((ind) => (
                      <SparkCard key={ind.code} ind={ind} spark={sparks.get(ind.code)} />
                    ))}
                  </div>
                  {g.rows.length > GROUP_CAP && (
                    <button
                      type="button"
                      className="btn ghost small show-all"
                      onClick={() =>
                        setExpanded((prev) => {
                          const next = new Set(prev);
                          if (next.has(g.source)) next.delete(g.source);
                          else next.add(g.source);
                          return next;
                        })
                      }
                    >
                      {isExpanded ? "Show fewer" : `Show all ${g.rows.length} →`}
                    </button>
                  )}
                </div>
              );
            })}
          </>
        )}
      </section>

      <p className="attribution">
        {sources.length > 0
          ? `Sources: ${sources.join(", ")}. Every figure links to its full series with provenance.`
          : "Sources will appear here as data is loaded."}
      </p>
    </main>
  );
}
