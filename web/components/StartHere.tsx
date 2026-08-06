// The landing page's "here is what is worth your time" band. A server
// component: the entries are static curation (lib/featured.ts), so there is no
// reason to ship JavaScript for them.

import Link from "next/link";
import { FEATURED } from "@/lib/featured";

export default function StartHere() {
  return (
    <div className="featured-grid">
      {FEATURED.map((f) => (
        <Link key={f.label} href={f.href} className="featured-card">
          <div className="featured-head">
            <h3>{f.label}</h3>
            {f.fresh && <span className="pill-new">New</span>}
          </div>
          <p>{f.note}</p>
          <p className="featured-source">{f.source}</p>
        </Link>
      ))}
    </div>
  );
}
