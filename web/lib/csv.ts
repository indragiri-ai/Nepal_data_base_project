// Client-side CSV download — the "take the data with you" affordance.
// Rows are quoted defensively; a UTF-8 BOM keeps Excel happy with any
// non-ASCII period labels or source names.

function quote(cell: string): string {
  return /[",\n]/.test(cell) ? `"${cell.replace(/"/g, '""')}"` : cell;
}

export function downloadCsv(filename: string, rows: string[][]): void {
  const body = rows.map((r) => r.map(quote).join(",")).join("\r\n");
  const blob = new Blob([`﻿${body}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
