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

// Deduplicate React mounts and queue charts so normal page loads stay within
// the server's simultaneous-request allowance. No automatic retry/pagination.
const pending = new Map<string, Promise<unknown>>();
const cached = new Map<string, { expires: number; value: unknown }>();
const waiting: Array<() => void> = [];
let active = 0;

async function getJson<T>(path: string): Promise<T> {
  const hit = cached.get(path);
  if (hit && hit.expires > Date.now()) return hit.value as T;
  const running = pending.get(path);
  if (running) return running as Promise<T>;
  const request = (async () => {
    if (active >= 3) await new Promise<void>((resolve) => waiting.push(resolve));
    else active += 1;
    try {
      const value = await requestJson<T>(path);
      if (cached.size >= 150) cached.delete(cached.keys().next().value!);
      cached.set(path, { expires: Date.now() + 60_000, value });
      return value;
    } finally {
      const next = waiting.shift();
      if (next) next();
      else active -= 1;
    }
  })();
  pending.set(path, request);
  try { return await request; }
  finally { pending.delete(path); }
}

async function requestJson<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { cache: "no-store", signal: AbortSignal.timeout(25_000) });
  } catch {
    // Network-level failure: API not running, CORS, DNS, offline.
    throw new ApiError(
      "The data service could not be reached. Please try again shortly.",
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
    if (res.status === 429) detail += ` Try again in ${res.headers.get("Retry-After") ?? "a few"} seconds.`;
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
export function fetchIndicatorSparks(codes: string[]): Promise<IndicatorSpark[]> {
  const params = new URLSearchParams();
  codes.forEach((code) => params.append("codes", code));
  return getJson<IndicatorSpark[]>(`/v1/indicators/spark?${params}`);
}

export type GeoLevel = "province" | "district" | "local_unit";

export function fetchGeoValues(
  indicatorCode: string,
  level: GeoLevel,
  parent?: string,
): Promise<GeoDataResponse> {
  const params = new URLSearchParams({ indicator: indicatorCode, level });
  if (parent) params.set("parent", parent);
  return getJson<GeoDataResponse>(`/v1/data/geo?${params.toString()}`);
}

export function fetchSeries(indicatorCode: string, geo = "NP"): Promise<DataResponse> {
  const params = new URLSearchParams({ indicator: indicatorCode, geo });
  return getJson<DataResponse>(`/v1/data?${params.toString()}`);
}

/** One slice of a broken-down series — e.g. a single commodity's daily prices.
 *  Without this a chart of one vegetable would have to download all 25, since
 *  the Kalimati series is ~77,000 observations per indicator. */
export function fetchSeriesSlice(
  indicatorCode: string,
  geo: string,
  breakdownKey: string,
  breakdownValue: string,
  start?: string,
  end?: string,
): Promise<DataResponse> {
  const params = new URLSearchParams({
    indicator: indicatorCode,
    geo,
    breakdown_key: breakdownKey,
    breakdown_value: breakdownValue,
  });
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  return getJson<DataResponse>(`/v1/data?${params.toString()}`);
}

/** One geography's value for one breakdown value — e.g. one party's votes in
 *  one district. `geo` is the P-code; `key` is the breakdown value. */
export interface GeoBreakdownCell {
  geo: string;
  key: string;
  value: number;
}

export interface GeoBreakdownResponse {
  indicator: IndicatorSummary;
  level: string;
  period: string;
  breakdown_key: string;
  unit_code: string;
  unit_name: string;
  provenance: Provenance;
  /** `value` here is the geography's TOTAL across the breakdown. */
  geographies: GeoValue[];
  cells: GeoBreakdownCell[];
}

/** A broken-down choropleth in one request: every breakdown value for every
 *  geography, for ONE period, plus each geography's total.
 *
 *  `fetchGeoValues` cannot serve election data — it returns only headline rows
 *  (no breakdowns), and every election observation carries a party. Always pass
 *  `period` when a source holds more than one, or the map will draw one period
 *  under another's label. */
export function fetchGeoBreakdown(
  indicatorCode: string,
  level: GeoLevel,
  breakdownKey: string,
  period?: string,
  /** One value of the breakdown (a single party's map). Omit for every value,
   *  which is what a stacked or share map needs. */
  breakdownValue?: string,
): Promise<GeoBreakdownResponse> {
  const params = new URLSearchParams({
    indicator: indicatorCode,
    level,
    breakdown_key: breakdownKey,
  });
  if (period) params.set("period", period);
  if (breakdownValue) params.set("breakdown_value", breakdownValue);
  return getJson<GeoBreakdownResponse>(`/v1/data/geo/breakdown?${params.toString()}`);
}

export interface SeasonalityPoint {
  breakdown_value: string;
  month: number;
  mean_value: number;
  days: number;
}

export interface SeasonalityResponse {
  indicator: IndicatorSummary;
  geography_code: string;
  unit_code: string;
  unit_name: string;
  breakdown_key: string;
  provenance: Provenance;
  points: SeasonalityPoint[];
}

/** Every January collapsed into one number, per breakdown value — the whole
 *  seasonal grid in ONE request instead of ~100,000 observations. */
export function fetchSeasonality(
  indicatorCode: string,
  geo: string,
  breakdownKey: string,
): Promise<SeasonalityResponse> {
  const params = new URLSearchParams({
    indicator: indicatorCode,
    geo,
    breakdown_key: breakdownKey,
  });
  return getJson<SeasonalityResponse>(`/v1/data/seasonality?${params.toString()}`);
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

/** One global-search match (SRCH.S1). `kind` is "indicator" (a dataset that can
 *  be charted) or "geography" (a place). `detail` is the indicator's topic or
 *  the geography's level; `unit` is null for places. */
export interface SearchHit {
  kind: "indicator" | "geography";
  code: string;
  name: string;
  name_ne: string | null;
  detail: string;
  unit: string | null;
}

export interface SearchResponse {
  query: string;
  total: number;
  results: SearchHit[];
}

/** Search every indicator and place in the warehouse. Matches English and
 *  Nepali text. The API rejects queries shorter than two characters (422), so
 *  callers should not send them. */
export function fetchSearch(query: string, limit = 30): Promise<SearchResponse> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  return getJson<SearchResponse>(`/v1/search?${params.toString()}`);
}

/** Where a search hit leads.
 *
 *  Indicators: /explore charts any annual series by code, EXCEPT the NRB
 *  monthly banking series, which /explore deliberately filters out and
 *  /banking owns — so those route to /banking instead.
 *
 *  Places: /population does not yet read a geography from the URL, so a place
 *  links to the map itself rather than to a deep link that would be silently
 *  ignored. Deep-linking a place is SRCH.S2 work. */
export function hrefForHit(hit: SearchHit): string {
  if (hit.kind === "geography") return "/population";
  if (hit.code.startsWith("NRB_")) {
    return `/banking?indicator=${encodeURIComponent(hit.code)}`;
  }
  return `/explore?indicator=${encodeURIComponent(hit.code)}`;
}

/** A human-friendly label for a topic slug (e.g. "economy" -> "Economy"). */
export function topicLabel(topic: string): string {
  return topic
    .split(/[_\s]+/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}
