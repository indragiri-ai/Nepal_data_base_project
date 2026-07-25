// Typed client for the Nepal Data Portal API (P1.S11).
//
// The browser talks ONLY to the API here — never to the database directly
// (Master Prompt §3.5). Types mirror api/models.py exactly; if the API contract
// changes, update both sides together.

// Where the API lives. Locally this is http://localhost:8000; in deployment it
// comes from NEXT_PUBLIC_API_BASE (inlined at build time). Render's blueprint
// wires this from the API service's host, which has no scheme — so default to
// https:// when one is missing.
function resolveApiBase(raw: string | undefined): string {
  const value = raw?.trim().replace(/\/$/, "");
  if (!value) return "http://localhost:8000";
  return /^https?:\/\//.test(value) ? value : `https://${value}`;
}

const API_BASE = resolveApiBase(process.env.NEXT_PUBLIC_API_BASE);

export interface IndicatorSummary {
  code: string;
  name: string;
  topic: string;
  unit: string;
  /** Headline-answer policy (decision 0005), from /v1/indicators. `source` is
   *  where this indicator's data comes from; `preferred_source` is the headline
   *  source for its concept. When they differ, this series is an alternative
   *  estimate. Absent on the single-indicator responses. */
  source?: string | null;
  preferred_source?: string | null;
}

export interface Provenance {
  source: string;
  dataset: string;
  license: string | null;
  latest_release_date: string;
}

export interface Observation {
  period: string;
  value: number;
  status: string;
  footnote: string | null;
  release_date: string;
  /** e.g. {"bfi_class": "commercial_banks"} for NRB banking series; empty or
   *  absent for country-level series (World Bank). */
  breakdowns?: Record<string, string>;
}

export interface DataResponse {
  indicator: IndicatorSummary;
  geography_code: string;
  geography_name: string;
  unit_code: string;
  unit_name: string;
  provenance: Provenance;
  observations: Observation[];
}

/** Raised when the API responds but with an error status (e.g. 404). */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function getJson<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  } catch {
    // Network-level failure: API not running, CORS, DNS, offline.
    throw new ApiError(
      `Couldn't reach the data service at ${API_BASE}. Is the API running (make api)?`,
      0,
    );
  }
  if (!res.ok) {
    let detail = `Request failed (HTTP ${res.status}).`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* response had no JSON body; keep the generic message */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

export interface GeoValue {
  geo_code: string;
  name: string;
  name_ne: string | null;
  value: number;
}

export interface GeoDataResponse {
  indicator: IndicatorSummary;
  level: string;
  period: string;
  unit_code: string;
  unit_name: string;
  provenance: Provenance;
  values: GeoValue[];
}

export function fetchIndicators(): Promise<IndicatorSummary[]> {
  return getJson<IndicatorSummary[]>("/v1/indicators");
}

/** One indicator's latest value + a short recent trend, for the sector cards. */
export interface IndicatorSpark {
  code: string;
  latest_period: string;
  latest_value: number;
  points: number[];
}

/** Every indicator's latest value + sparkline points in a single request — the
 *  data behind the sector-page cards (avoids one fetch per indicator). */
export function fetchIndicatorSparks(): Promise<IndicatorSpark[]> {
  return getJson<IndicatorSpark[]>("/v1/indicators/spark");
}

export function fetchGeoValues(
  indicatorCode: string,
  level: "province" | "district",
): Promise<GeoDataResponse> {
  const params = new URLSearchParams({ indicator: indicatorCode, level });
  return getJson<GeoDataResponse>(`/v1/data/geo?${params.toString()}`);
}

export function fetchSeries(indicatorCode: string, geo = "NP"): Promise<DataResponse> {
  const params = new URLSearchParams({ indicator: indicatorCode, geo });
  return getJson<DataResponse>(`/v1/data?${params.toString()}`);
}

export interface DatasetMeta {
  dataset: string;
  source: string;
  last_updated: string | null;
  latest_release_date: string | null;
}

export interface MetaResponse {
  /** Most recent successful ingestion across all datasets — the footer date. */
  data_updated: string | null;
  datasets: DatasetMeta[];
}

export function fetchMeta(): Promise<MetaResponse> {
  return getJson<MetaResponse>("/v1/meta");
}

/** A human-friendly label for a topic slug (e.g. "economy" -> "Economy"). */
export function topicLabel(topic: string): string {
  return topic
    .split(/[_\s]+/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}
