// Bank-class palette + series shape, in a chart-free module so the dashboard
// can import colors for its chips WITHOUT pulling ECharts into the eager
// bundle (the chart itself stays behind a dynamic import).
//
// Validated categorical slots (dataviz six-checks, light surface #ffffff).
// The ORDER is the colorblind-safety mechanism — assign by entity, never
// re-order, never cycle.

export const CLASS_COLORS: Record<string, string> = {
  overall: "#008300", // slot 1 — green
  commercial_banks: "#2a78d6", // slot 2 — blue
  development_banks: "#c98500", // slot 3 — amber
  finance_companies: "#4a3aa7", // slot 4 — violet
};

/** One chart line: a BFI class's monthly series. */
export interface ClassSeries {
  bfiClass: string;
  label: string;
  periods: string[]; // e.g. "Mid-May 2026"
  values: (number | null)[]; // aligned to periods; null = no data that month
}
