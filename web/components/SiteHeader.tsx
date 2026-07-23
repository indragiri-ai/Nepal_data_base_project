"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { SECTORS } from "@/lib/sectors";

const SECTOR_SLUGS = new Set(SECTORS.map((s) => `/${s.slug}`));

/** Brand mark: an abstract twin-pennant — Nepal's flag reduced to two strokes. */
function Mark() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" className="mark">
      <path
        d="M5 2v20M5 2l11 5.5L5 13M5 11l9 4.5L5 20"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function SiteHeader() {
  const pathname = usePathname();
  const onSector = SECTOR_SLUGS.has(pathname);
  return (
    <header className="site-header">
      <div className="shell bar">
        <Link href="/" className="brand" aria-label="Nepal Data Portal — home">
          <Mark />
          <span className="name">Nepal Data Portal</span>
        </Link>
        <nav className="site-nav" aria-label="Main">
          <Link href="/" aria-current={pathname === "/" ? "page" : undefined}>
            Overview
          </Link>
          <details className="nav-dd">
            <summary aria-current={onSector ? "page" : undefined}>Data</summary>
            <ul className="nav-dd-panel">
              {SECTORS.map((s) => (
                <li key={s.slug}>
                  <Link href={`/${s.slug}`}>{s.title}</Link>
                </li>
              ))}
            </ul>
          </details>
          <Link
            href="/population"
            aria-current={pathname === "/population" ? "page" : undefined}
          >
            Population map
          </Link>
          <Link
            href="/banking"
            aria-current={pathname === "/banking" ? "page" : undefined}
          >
            Banking
          </Link>
        </nav>
      </div>
    </header>
  );
}
