"use client";

// The "Browse by sector" grid below the landing hero: all 8 sectors as cards
// with a live indicator count. Fetches the indicator list once and counts per
// sector via lib/sectors — no chart JS on this route.

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { fetchIndicators, type IndicatorSummary } from "@/lib/api";
import { SECTORS, indicatorsForSector } from "@/lib/sectors";

const S = 1.8;
const icons: Record<string, ReactNode> = {
  economy: (
    <path d="M3 20h18M5 20V10m5 10V4m5 16v-8m5 8V7" strokeWidth={S} strokeLinecap="round" />
  ),
  finance: (
    <path
      d="M3 9.5 12 4l9 5.5M5 10v7m4.5-7v7m5-7v7m4.5-7v7M3 20h18"
      strokeWidth={S}
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  ),
  people: (
    <path
      d="M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm-5.5 9a5.5 5.5 0 0 1 11 0M16 5.5a3 3 0 0 1 0 6m2.5 8.5a5.5 5.5 0 0 0-3.5-5.1"
      strokeWidth={S}
      strokeLinecap="round"
    />
  ),
  health: (
    <path
      d="M3 12h4l2-5 3 10 2.5-7L18 12h3"
      strokeWidth={S}
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  ),
  education: (
    <path
      d="M12 7c-2-1.5-5-1.5-8-1v11c3-.5 6-.5 8 1 2-1.5 5-1.5 8-1V6c-3-.5-6-.5-8 1Zm0 0v11"
      strokeWidth={S}
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  ),
  labor: (
    <path
      d="M4 8h16v11H4zM9 8V6a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"
      strokeWidth={S}
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  ),
  environment: (
    <path
      d="M5 19c8 1 14-4 14-13-6 0-13 2-13 8 0 2 1 4 3 5m0 0c-1-3 1-6 4-8"
      strokeWidth={S}
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  ),
  governance: (
    <path
      d="M4 21h16M4 10h16M12 3 4 7h16l-8-4ZM6 10v11m4-11v11m4-11v11m4-11v11"
      strokeWidth={S}
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  ),
};

export default function SectorCards() {
  const [indicators, setIndicators] = useState<IndicatorSummary[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchIndicators()
      .then((all) => {
        if (!cancelled) setIndicators(all);
      })
      .catch(() => {
        /* counts are optional — cards still work without them */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="sector-grid">
      {SECTORS.map((sector) => {
        const count = indicators
          ? indicatorsForSector(sector, indicators).length
          : null;
        return (
          <Link href={`/${sector.slug}`} className="sector-card" key={sector.slug}>
            <svg viewBox="0 0 24 24" fill="none" className="icon" aria-hidden="true">
              {icons[sector.slug]}
            </svg>
            <h3>{sector.title}</h3>
            <p>{sector.description}</p>
            <span className="meta">
              {count === null ? (
                <span className="skeleton" aria-hidden="true">
                  loading
                </span>
              ) : count > 0 ? (
                `${count} indicator${count === 1 ? "" : "s"}`
              ) : (
                "in preparation"
              )}
            </span>
            <span className="go">Open {sector.titleShort} →</span>
          </Link>
        );
      })}
    </div>
  );
}
