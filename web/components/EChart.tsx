"use client";

// Thin React wrapper over a MODULAR ECharts build.
//
// We register only what the portal draws — line charts, grid, tooltip,
// legend, canvas — instead of importing all of ECharts. This is the single
// biggest first-load-JS saving on the site; if a new chart form is added
// (bar, map), register its module here and nowhere else.

import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { LineChart, type LineSeriesOption } from "echarts/charts";
import {
  GridComponent,
  type GridComponentOption,
  LegendComponent,
  type LegendComponentOption,
  TooltipComponent,
  type TooltipComponentOption,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

export type ChartOption = echarts.ComposeOption<
  LineSeriesOption | GridComponentOption | LegendComponentOption | TooltipComponentOption
>;

/** Chrome shared by every chart on the site — recessive by design. */
export const CHART_INK = {
  axisLabel: "#8a91a0",
  axisLine: "#d8d4c8",
  grid: "#eeece5",
  text: "#1b2436",
  secondary: "#545d6e",
};

/** Tooltip styling shared by every chart. */
export const TOOLTIP_STYLE = {
  backgroundColor: "#ffffff",
  borderColor: "#e5e2d9",
  borderWidth: 1,
  padding: [10, 14] as [number, number],
  textStyle: { color: CHART_INK.text, fontSize: 13 },
  extraCssText:
    "box-shadow: 0 6px 24px -8px rgba(27,36,54,0.18); border-radius: 8px;",
  confine: true,
};

export default function EChart({
  option,
  height,
  ariaLabel,
}: {
  option: ChartOption;
  height: number;
  ariaLabel: string;
}) {
  const holder = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    const el = holder.current;
    if (!el) return;
    const instance = echarts.init(el);
    chart.current = instance;
    const ro = new ResizeObserver(() => instance.resize());
    ro.observe(el);
    return () => {
      ro.disconnect();
      instance.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    chart.current?.setOption(option, { notMerge: true });
  }, [option]);

  // role="img": the canvas is opaque to assistive tech; the label describes it
  // and the data table nearby is the accessible equivalent.
  return <div ref={holder} style={{ height, width: "100%" }} role="img" aria-label={ariaLabel} />;
}
