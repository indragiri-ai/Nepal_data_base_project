"use client";

// The header search box (SRCH.S1) — one field over every indicator and place
// in the warehouse. Submitting navigates to /search?q=…; the results page does
// the fetching, so a slow API never blocks typing.

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

/** Below this the API returns 422, so the form refuses to submit instead. */
const MIN_QUERY = 2;

/** True when the user is typing somewhere else and "/" should stay a slash. */
function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  const tag = el.tagName;
  return (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT" ||
    el.isContentEditable
  );
}

export default function SearchBox({ initialQuery = "" }: { initialQuery?: string }) {
  const router = useRouter();
  const [value, setValue] = useState(initialQuery);
  const inputRef = useRef<HTMLInputElement>(null);

  // "/" focuses the box — the convention on data and documentation sites.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
      if (isTypingTarget(e.target)) return;
      e.preventDefault();
      inputRef.current?.focus();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const trimmed = value.trim();
  const tooShort = trimmed.length > 0 && trimmed.length < MIN_QUERY;

  return (
    <form
      className="search-box"
      role="search"
      onSubmit={(e) => {
        e.preventDefault();
        if (trimmed.length < MIN_QUERY) return;
        router.push(`/search?q=${encodeURIComponent(trimmed)}`);
      }}
    >
      <label className="sr-only" htmlFor="site-search">
        Search all data
      </label>
      <svg className="search-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
        <path d="M16.5 16.5L21 21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
      <input
        id="site-search"
        ref={inputRef}
        type="search"
        name="q"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Search data and places…"
        autoComplete="off"
        aria-describedby={tooShort ? "site-search-hint" : undefined}
      />
      {tooShort && (
        <span id="site-search-hint" className="sr-only">
          Type at least {MIN_QUERY} characters to search.
        </span>
      )}
    </form>
  );
}
