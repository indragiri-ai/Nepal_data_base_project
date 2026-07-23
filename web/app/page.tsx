import type { Metadata } from "next";
import Link from "next/link";
import HeroStats from "@/components/HeroStats";
import DataOrbit from "@/components/DataOrbit";
import SectorCards from "@/components/SectorCards";

export const metadata: Metadata = {
  title: "Nepal Data Portal — trustworthy data about Nepal",
};

export default function HomePage() {
  return (
    <main className="page">
      <section className="hero">
        <div className="hero-orbit">
          <div className="hero-copy">
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
              <Link className="btn ghost" href="#sectors">
                Browse sectors
              </Link>
            </div>
          </div>
          <DataOrbit />
        </div>
        <HeroStats />
      </section>

      <section id="sectors" aria-labelledby="sections-title">
        <div className="section-head">
          <h2 id="sections-title">Browse by sector</h2>
          <p>
            The portal is organised the way Nepal&rsquo;s questions are asked —
            by sector, with the source alongside every series.
          </p>
        </div>
        <SectorCards />
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
