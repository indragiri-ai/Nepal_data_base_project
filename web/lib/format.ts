// Number formatting shared by charts, tables, and stat tiles.

const nf = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
const compact = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});

/** Format a value with its unit for tooltips, tables, and tiles. */
export function formatValue(value: number, unitCode: string): string {
  switch (unitCode) {
    case "PCT":
      return `${nf.format(value)}%`;
    case "USD":
      return `US$ ${nf.format(value)}`;
    default:
      return nf.format(value);
  }
}

/** Compact axis labels so large series stay readable (e.g. 30B, 28M). */
export function formatAxis(value: number, unitCode: string): string {
  if (unitCode === "USD" || unitCode === "COUNT") return compact.format(value);
  return formatValue(value, unitCode);
}

/** Compact headline figure for stat tiles (29.2M people, US$ 40.9B). */
export function formatCompact(value: number): string {
  return compact.format(value);
}

/** Signed change between two values, in the series' own unit terms. */
export function formatDelta(latest: number, previous: number, unitCode: string): string {
  const d = latest - previous;
  const sign = d >= 0 ? "+" : "−";
  const abs = Math.abs(d);
  const body = unitCode === "PCT" ? `${nf.format(abs)} pp` : compact.format(abs);
  return `${sign}${body}`;
}
