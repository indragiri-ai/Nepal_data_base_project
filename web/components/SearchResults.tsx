"use client";

// Search results (SRCH.S1). Reads ?q= and renders the matches grouped into
// datasets and places. Uses useSearchParams rather than reading
// window.location once on mount, so searching again from the header while
// already on this page re-runs the query.

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  ApiError,
  fetchSearch,
  hrefForHit,
  topicLabel,
  type SearchHit,
  type SearchResponse,
} from "@/lib/api";
import SearchBox from "@/components/SearchBox";

const MIN_QUERY = 2;

function messageFor(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  return "Something went wrong running that search.";
}

/** Place levels read as plain words, not database enum values. */
const LEVEL_LABEL: Record<string, string> = {
  country: "Country",
  province: "Province",
  district: "District",
  local_unit: "Municipality",
  old_region: "Region (pre-2015)",
  old_district: "District (pre-2015)",
};

function detailLabel(hit: SearchHit): string {
  return hit.kind === "geography"
    ? (LEVEL_LABEL[hit.detail] ?? hit.detail)
    : topicLabel(hit.detail);
}

function HitList({ hits, title, note }: { hits: SearchHit[]; title: string; note: string }) {
  if (hits.length === 0) return null;
  return (
    <section className="search-group">
      <h2>
        {title} <span className="count">{hits.length}</span>
      </h2>
      <p className="group-note">{note}</p>
      <ul className="search-hits">
        {hits.map((hit) => (
          <li key={`${hit.kind}:${hit.code}`}>
            <Link href={hrefForHit(hit)}>
              <span className="hit-name">
                {hit.name}
                {hit.name_ne && <span className="hit-ne"> · {hit.name_ne}</span>}
              </span>
              <span className="hit-meta">
                <span className="tag">{detailLabel(hit)}</span>
                {hit.unit && <span className="unit">{hit.unit}</span>}
                <code>{hit.code}</code>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function SearchResults() {
  const params = useSearchParams();
  const query = (params.get("q") ?? "").trim();

  const [data, setData] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (query.length < MIN_QUERY) {
      setData(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchSearch(query)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err) => {
        if (!cancelled) {
          setData(null);
          setError(messageFor(err));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query]);

  const indicators = data?.results.filter((r) => r.kind === "indicator") ?? [];
  const places = data?.results.filter((r) => r.kind === "geography") ?? [];

  return (
    <div className="shell search-page">
      <h1>Search</h1>
      <div className="search-page-box">
        <SearchBox initialQuery={query} />
      </div>

      {query.length === 0 && (
        <p className="state">
          Search every dataset and place in the portal — in English or Nepali. Try{" "}
          <Link href="/search?q=literacy">literacy</Link> or{" "}
          <Link href="/search?q=Sarlahi">Sarlahi</Link>.
        </p>
      )}

      {query.length > 0 && query.length < MIN_QUERY && (
        <p className="state">Type at least {MIN_QUERY} characters to search.</p>
      )}

      {loading && <p className="state">Searching…</p>}

      {error && (
        <p className="state error" role="alert">
          {error}
        </p>
      )}

      {data && !loading && data.total === 0 && (
        <p className="state">
          Nothing in the portal matches <strong>{data.query}</strong> yet. That may mean the
          data has not been added — the portal only lists what it actually holds. Try{" "}
          <Link href="/search?q=literacy">literacy</Link> or{" "}
          <Link href="/search?q=Sarlahi">Sarlahi</Link>.
        </p>
      )}

      {data && !loading && data.total > 0 && (
        <>
          <p className="search-summary">
            {data.total} {data.total === 1 ? "match" : "matches"} for{" "}
            <strong>{data.query}</strong>
          </p>
          <HitList
            hits={indicators}
            title="Datasets"
            note="Series the portal can chart, with their source."
          />
          <HitList
            hits={places}
            title="Places"
            note="Provinces, districts and municipalities on the census map."
          />
        </>
      )}
    </div>
  );
}
