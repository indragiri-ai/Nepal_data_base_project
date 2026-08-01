import { Suspense } from "react";
import type { Metadata } from "next";
import SearchResults from "@/components/SearchResults";

export const metadata: Metadata = {
  title: "Search",
  description:
    "Search every dataset and place in the Nepal Data Portal — census topics, World Bank indicators, banking series, provinces, districts and municipalities. English or Nepali.",
};

// useSearchParams needs a Suspense boundary; without one the whole route is
// forced to client-side rendering at build time.
export default function SearchPage() {
  return (
    <Suspense fallback={<div className="shell search-page"><p className="state">Loading search…</p></div>}>
      <SearchResults />
    </Suspense>
  );
}
