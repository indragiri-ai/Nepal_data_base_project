"use client";

// Multi-series monthly lines — the Banking dashboard's chart.
//
// Colors are the portal's validated categorical palette (dataviz six-checks,
// light surface): the ORDER is the colorblind-safety mechanism — assign by
// entity, never re-order, never cycle. ≥2 series ⇒ legend always shown; the
// data table below is the accessible equivalent.

import EChart, { CHART_INK, TOOLTIP_STYLE, type ChartOption } from "@/components/EChart";
import { formatAxis, formatValue } from "@/lib/format";
import { CLASS_COLORS, type ClassSeries } from "@/lib/bankingPalette";

export type { ClassSeries };

export default function MultiLineChart({
  series,
  unitCode,
  unitName,
}: {
  series: ClassSeries[];
  unitCode: string;
  unitName: string;
}) {
  const periods = series[0]?.periods ?? [];

  const option: ChartOption = {
    grid: { left: 8, right: 20, top: 44, bottom: 8, containLabel: true },
    legend: {
      top: 0,
      left: 0,
      icon: "roundRect",
      itemWidth: 14,
      itemHeight: 6,
      itemGap: 18,
      data: series.map((s) => s.label),
      textStyle: { color: CHART_INK.secondary, fontSize: 12 },
    },
    tooltip: {
      ...TOOLTIP_STYLE,
      trigger: "axis",
      axisPointer: {
        type: "line",
        lineStyle: { color: CHART_INK.axisLine, type: "dashed", width: 1 },
      },
      valueFormatter: (v) => (v == null ? "—" : formatValue(v as number, unitCode)),
    },
    xAxis: {
      type: "category",
      data: periods,
      boundaryGap: false,
      axisLabel: { color: CHART_INK.axisLabel, fontSize: 11, hideOverlap: true },
      axisLine: { lineStyle: { color: CHART_INK.axisLine } },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      scale: true,
      axisLabel: {
        color: CHART_INK.axisLabel,
        fontSize: 11,
        formatter: (value: number) => formatAxis(value, unitCode),
      },
      splitLine: { lineStyle: { color: CHART_INK.grid } },
    },
    series: series.map((s) => ({
      name: s.label,
      type: "line" as const,
      data: s.values,
      smooth: 0.15,
      showSymbol: false,
      connectNulls: false,
      lineStyle: {
        width: s.bfiClass === "overall" ? 2.5 : 2,
        color: CLASS_COLORS[s.bfiClass] ?? CHART_INK.secondary,
      },
      itemStyle: { color: CLASS_COLORS[s.bfiClass] ?? CHART_INK.secondary },
      emphasis: { focus: "series" as const },
    })),
  };

  return (
    <EChart
      option={option}
      height={440}
      ariaLabel={`Line chart comparing ${series
        .map((s) => s.label)
        .join(", ")} — ${unitName}, monthly. The same data is available in the table below.`}
    />
  );
}
