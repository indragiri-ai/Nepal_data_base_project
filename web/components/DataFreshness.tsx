"use client";

// "Data updated: {date}" line in the site footer. Fetches /v1/meta client-side
// (the browser talks only to the API) and fails silently — a freshness line is
// nice-to-have, so if the API is briefly unreachable the footer just omits it
// rather than showing an error.

import { useEffect, useState } from "react";
import { fetchMeta } from "@/lib/api";

function formatDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export default function DataFreshness() {
  const [updated, setUpdated] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchMeta()
      .then((meta) => {
        if (!cancelled) setUpdated(meta.data_updated);
      })
      .catch(() => {
        /* freshness is optional — keep the footer clean on failure */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!updated) return null;

  return (
    <span className="data-freshness">
      Data last updated <time dateTime={updated}>{formatDate(updated)}</time>.
    </span>
  );
}
