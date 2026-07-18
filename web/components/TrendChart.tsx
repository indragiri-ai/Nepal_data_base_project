"use client";

// Single-series time trend — the Explore page's chart.
// One series needs no legend (the title names it); a crosshair tooltip is
// the default interaction for a line.

import EChart, { CHART_INK, TOOLTIP_STYLE, type ChartOption } from "@/components/EChart";
import { formatAxis, formatValue } from "@/lib/format";
import type { DataResponse } from "@/lib/api";

const LINE = "#bb2340"; // brand crimson; 7.5:1 on the white card

export default function TrendChart({ data }: { data: DataResponse }) {
  const periods = data.observations.map((o) => o.period);
  const values = data.observations.map((o) => o.value);
  const unitCode = data.unit_code;

  const option: ChartOption = {
    grid: { left: 8, right: 20, top: 28, bottom: 8, containLabel: true },
    tooltip: {
      ...TOOLTIP_STYLE,
      trigger: "axis",
      axisPointer: {
        type: "line",
        lineStyle: { color: CHART_INK.axisLine, type: "dashed", width: 1 },
      },
      formatter: (params) => {
        const arr = params as unknown as Array<{ axisValue: string; data: number }>;
        const p = arr[0];
        return `<div style="font-weight:650;margin-bottom:2px">${p.axisValue}</div>
          <div style="color:${CHART_INK.secondary};font-size:12px">${data.indicator.name}</div>
          <div style="font-weight:650;font-size:15px;margin-top:2px">${formatValue(p.data, unitCode)}</div>`;
      },
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
    series: [
      {
        name: data.indicator.name,
        type: "line",
        data: values,
        smooth: 0.15,
        showSymbol: false,
        lineStyle: { width: 2, color: LINE },
        itemStyle: { color: LINE },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(187,35,64,0.08)" },
              { offset: 1, color: "rgba(187,35,64,0)" },
            ],
          },
        },
        emphasis: { focus: "series" },
      },
    ],
  };

  return (
    <EChart
      option={option}
      height={420}
      ariaLabel={`Line chart of ${data.indicator.name} for ${data.geography_name}, ${
        periods[0] ?? ""
      } to ${periods[periods.length - 1] ?? ""}. The same data is available in the table below.`}
    />
  );
}
