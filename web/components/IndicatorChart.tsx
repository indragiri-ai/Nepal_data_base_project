"use client";

import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import type { DataResponse } from "@/lib/api";

/** Format a value with its unit for tooltips and axes. */
export function formatValue(value: number, unitCode: string): string {
  const n = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);
  switch (unitCode) {
    case "PCT":
      return `${n}%`;
    case "USD":
      return `US$ ${n}`;
    default:
      return n;
  }
}

/** Compact axis labels so large currency series stay readable (e.g. 30B). */
function formatAxis(value: number, unitCode: string): string {
  if (unitCode === "USD") {
    return new Intl.NumberFormat("en-US", {
      notation: "compact",
      maximumFractionDigits: 1,
    }).format(value);
  }
  return formatValue(value, unitCode);
}

export default function IndicatorChart({ data }: { data: DataResponse }) {
  const periods = data.observations.map((o) => o.period);
  const values = data.observations.map((o) => o.value);
  const unitCode = data.unit_code;

  const option: EChartsOption = {
    grid: { left: 8, right: 24, top: 24, bottom: 8, containLabel: true },
    tooltip: {
      trigger: "axis",
      formatter: (params) => {
        const arr = params as unknown as Array<{ axisValue: string; data: number }>;
        const p = arr[0];
        return `<strong>${p.axisValue}</strong><br/>${data.indicator.name}<br/><strong>${formatValue(
          p.data,
          unitCode,
        )}</strong> <span style="color:#64748b">(${data.unit_name})</span>`;
      },
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
        formatter: (value: number) => formatAxis(value, unitCode),
      },
      splitLine: { lineStyle: { color: "#eef2f7" } },
    },
    series: [
      {
        name: data.indicator.name,
        type: "line",
        data: values,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2.5, color: "#1d4ed8" },
        areaStyle: { color: "rgba(29,78,216,0.08)" },
        emphasis: { focus: "series" },
      },
    ],
  };

  return (
    <ReactECharts
      option={option}
      style={{ height: 420, width: "100%" }}
      notMerge
      opts={{ renderer: "canvas" }}
    />
  );
}
