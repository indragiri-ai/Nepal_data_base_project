"use client";

import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import { formatValue } from "@/components/IndicatorChart";

/** One chart line: a BFI class's monthly series. */
export interface ClassSeries {
  bfiClass: string; // "commercial_banks" | ... | "overall"
  label: string; // display name
  periods: string[]; // e.g. "Mid-May 2026"
  values: (number | null)[]; // aligned to `periods`; null = no data that month
}

/** Display colors per BFI class — stable across the dashboard. */
export const CLASS_COLORS: Record<string, string> = {
  overall: "#0f172a",
  commercial_banks: "#1d4ed8",
  development_banks: "#059669",
  finance_companies: "#d97706",
};

export default function BankingChart({
  series,
  unitCode,
  unitName,
}: {
  series: ClassSeries[];
  unitCode: string;
  unitName: string;
}) {
  // All series share one x-axis; the page aligns them before passing them in.
  const periods = series[0]?.periods ?? [];

  const option: EChartsOption = {
    grid: { left: 8, right: 24, top: 40, bottom: 8, containLabel: true },
    legend: {
      top: 0,
      data: series.map((s) => s.label),
      textStyle: { color: "#475569" },
    },
    tooltip: {
      trigger: "axis",
      valueFormatter: (v) =>
        v == null ? "—" : `${formatValue(v as number, unitCode)} (${unitName})`,
    },
    xAxis: {
      type: "category",
      data: periods,
      boundaryGap: false,
      axisLabel: { color: "#475569" },
      axisLine: { lineStyle: { color: "#cbd5e1" } },
    },
    yAxis: {
      type: "value",
      scale: true,
      axisLabel: {
        color: "#475569",
        formatter: (value: number) =>
          unitCode === "COUNT"
            ? new Intl.NumberFormat("en-US", {
                notation: "compact",
                maximumFractionDigits: 1,
              }).format(value)
            : formatValue(value, unitCode),
      },
      splitLine: { lineStyle: { color: "#eef2f7" } },
    },
    series: series.map((s) => ({
      name: s.label,
      type: "line",
      data: s.values,
      smooth: true,
      showSymbol: false,
      connectNulls: false,
      lineStyle: {
        width: s.bfiClass === "overall" ? 3 : 2,
        color: CLASS_COLORS[s.bfiClass] ?? "#64748b",
      },
      itemStyle: { color: CLASS_COLORS[s.bfiClass] ?? "#64748b" },
      emphasis: { focus: "series" },
    })),
  };

  return (
    <ReactECharts
      option={option}
      style={{ height: 440, width: "100%" }}
      notMerge
      opts={{ renderer: "canvas" }}
    />
  );
}
