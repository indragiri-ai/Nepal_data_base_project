import type { Metadata } from "next";
import Link from "next/link";
import HeroStats from "@/components/HeroStats";

export const metadata: Metadata = {
  title: "Nepal Data Portal — trustworthy data about Nepal",
};

/** Abstract Himalayan ridgeline — inline, a few hundred bytes, no image request. */
function Ridgeline() {
  return (
    <svg
      className="ridgeline"
      viewBox="0 0 480 220"
      fill="none"
      aria-hidden="true"
      preserveAspectRatio="xMaxYMid meet"
    >
      <path
        d="M0 200 L70 120 L110 160 L170 60 L215 130 L268 30 L320 140 L370 90 L420 150 L480 100"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <path
        d="M238 86 L268 30 L296 82"
        className="peak"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <path
        d="M0 214 L90 160 L150 190 L230 110 L300 180 L380 130 L480 176"
        stroke="currentColor"
        strokeWidth="1"
        strokeLinejoin="round"
        opacity="0.6"
      />
    </svg>
  );
}

const ICONS = {
  economy: (
    <svg viewBox="0 0 24 24" fill="none" className="icon" aria-hidden="true">
      <path
        d="M3 20h18M5 20V10m5 10V4m5 16v-8m5 8V7"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  ),
  banking: (
    <svg viewBox="0 0 24 24" fill="none" className="icon" aria-hidden="true">
      <path
        d="M3 9.5 12 4l9 5.5M5 10v7m4.5-7v7m5-7v7m4.5-7v7M3 20h18"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
  census: (
    <svg viewBox="0 0 24 24" fill="none" className="icon" aria-hidden="true">
      <path
        d="M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm-5.5 9a5.5 5.5 0 0 1 11 0M16 5.5a3 3 0 0 1 0 6m2.5 8.5a5.5 5.5 0 0 0-3.5-5.1"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  ),
};

export default function HomePage() {
  return (
    <main className="page">
      <section className="hero">
        <Ridgeline />
        <p className="eyebrow">Free · Open · Verifiable</p>
        <h1>Nepal&rsquo;s numbers, in one trustworthy place.</h1>
        <p className="lede">
          Official statistics about Nepal&rsquo;s economy, banking system, and
          society — collected from primary sources, archived untouched, and
          published with the provenance behind every figure.
        </p>
        <div className="cta-row">
          <Link className="btn primary" href="/explore">
            Explore the data
          </Link>
          <Link className="btn ghost" href="/banking">
            Banking dashboard
          </Link>
        </div>
        <HeroStats />
      </section>

      <section aria-labelledby="sections-title">
        <div className="section-head">
          <h2 id="sections-title">Browse by sector</h2>
          <p>
            The portal is organised the way Nepal&rsquo;s questions are asked —
            by sector, with the source alongside every series.
          </p>
        </div>
        <div className="sector-grid">
          <Link href="/explore" className="sector-card">
            {ICONS.economy}
            <h3>Economy &amp; society</h3>
            <p>
              GDP, inflation, trade, remittances, health, and education — six
              decades of annual series for Nepal.
            </p>
            <span className="meta">World Bank · annual · 1960–present</span>
            <span className="go">Open the explorer →</span>
          </Link>
          <Link href="/banking" className="sector-card">
            {ICONS.banking}
            <h3>Banking &amp; finance</h3>
            <p>
              35 monthly indicators from Nepal Rastra Bank — credit, deposits,
              liquidity, capital, interest rates, and financial access, by bank
              class.
            </p>
            <span className="meta">Nepal Rastra Bank · monthly · 2021–present</span>
            <span className="go">Open the dashboard →</span>
          </Link>
          <Link href="/population" className="sector-card">
            {ICONS.census}
            <h3>Population &amp; census</h3>
            <p>
              Census 2021 on the map of Nepal — population, density, sex ratio,
              growth, and literacy for every province and district.
            </p>
            <span className="meta">National Statistics Office · Census 2021</span>
            <span className="go">Open the map →</span>
          </Link>
        </div>
      </section>

      <section aria-labelledby="trust-title">
        <div className="section-head">
          <h2 id="trust-title">Why you can trust these numbers</h2>
        </div>
        <div className="trust">
          <div className="item">
            <h3>Source-first, always</h3>
            <p>
              Every file and API payload is archived exactly as published —
              fingerprinted and immutable — before anything is parsed from it.
            </p>
          </div>
          <div className="item">
            <h3>Nothing invented</h3>
            <p>
              Unknown values are reported, never estimated. When a source
              revises a figure, both the old and new values are kept, dated.
            </p>
          </div>
          <div className="item">
            <h3>Traceable to the release</h3>
            <p>
              Every chart names its source, dataset, release date, and licence —
              and the underlying data can be viewed and downloaded as a table.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
