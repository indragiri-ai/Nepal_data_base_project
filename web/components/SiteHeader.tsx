"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/explore", label: "Explore" },
  { href: "/banking", label: "Banking" },
  { href: "/population", label: "Population" },
];

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
  return (
    <header className="site-header">
      <div className="shell bar">
        <Link href="/" className="brand" aria-label="Nepal Data Portal — home">
          <Mark />
          <span className="name">Nepal Data Portal</span>
        </Link>
        <nav className="site-nav" aria-label="Main">
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              aria-current={pathname === l.href ? "page" : undefined}
            >
              {l.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
