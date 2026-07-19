"use client";

// Choropleth of Nepal — provinces or districts shaded by one indicator.
//
// Follows the dataviz method: SEQUENTIAL encoding = one hue, light→dark
// (the portal's blue ramp), continuous visual scale with draggable handles,
// hover tooltip on every region, recessive chrome. The data table on the
// page is the accessible equivalent of the map.
//
// Boundary files are simplified from mesaugat/geoJSON-Nepal (MIT; OCHA
// P-codes) — see reference/census/PROVENANCE.md. Regions join to warehouse
// values by P-code (our geography `code`), never by name.

import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { MapChart, type MapSeriesOption } from "echarts/charts";
import {
  TooltipComponent,
  type TooltipComponentOption,
  VisualMapComponent,
  type VisualMapComponentOption,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { CHART_INK, TOOLTIP_STYLE } from "@/components/EChart";
import { formatValue } from "@/lib/format";

echarts.use([MapChart, TooltipComponent, VisualMapComponent, CanvasRenderer]);

/** Sequential blue ramp (light→dark) — the portal's magnitude scale. */
const SEQUENTIAL_BLUES = [
  "#cde2fb",
  "#9ec5f4",
  "#6da7ec",
  "#3987e5",
  "#256abf",
  "#184f95",
  "#0d366b",
];

export interface RegionDatum {
  code: string; // P-code — joins the GeoJSON feature
  name: string;
  nameNe: string | null;
  value: number;
}

interface MapSpec {
  url: string;
  nameProperty: string;
}

const MAPS: Record<string, MapSpec> = {
  province: { url: "/maps/nepal-provinces.json", nameProperty: "ADM1_PCODE" },
  district: { url: "/maps/nepal-districts.json", nameProperty: "DIST_PCODE" },
};

const registered = new Set<string>();

async function ensureMap(level: string): Promise<void> {
  if (registered.has(level)) return;
  const res = await fetch(MAPS[level].url);
  if (!res.ok) throw new Error(`Couldn't load the ${level} map (HTTP ${res.status}).`);
  const geojson = await res.json();
  echarts.registerMap(`nepal-${level}`, geojson);
  registered.add(level);
}

type Option = echarts.ComposeOption<
  MapSeriesOption | TooltipComponentOption | VisualMapComponentOption
>;

export default function ChoroplethMap({
  level,
  data,
  unitCode,
  onError,
}: {
  level: "province" | "district";
  data: RegionDatum[];
  unitCode: string;
  onError: (message: string) => void;
}) {
  const holder = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const [mapReady, setMapReady] = useState<string | null>(null);

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
    let cancelled = false;
    ensureMap(level)
      .then(() => {
        if (!cancelled) setMapReady(level);
      })
      .catch((err) => {
        if (!cancelled) onError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [level, onError]);

  useEffect(() => {
    if (mapReady !== level || !chart.current || data.length === 0) return;

    const byCode = new Map(data.map((d) => [d.code, d]));
    const values = data.map((d) => d.value);
    const min = Math.min(...values);
    const max = Math.max(...values);

    const option: Option = {
      tooltip: {
        ...TOOLTIP_STYLE,
        trigger: "item",
        formatter: (params) => {
          const p = params as unknown as { name: string; value: number | undefined };
          const region = byCode.get(p.name);
          if (!region) return "";
          const ne = region.nameNe ? ` <span style="color:${CHART_INK.axisLabel}">${region.nameNe}</span>` : "";
          const val =
            typeof p.value === "number" && isFinite(p.value)
              ? formatValue(p.value, unitCode)
              : "no data";
          return `<div style="font-weight:650">${region.name}${ne}</div>
            <div style="font-weight:650;font-size:15px;margin-top:2px">${val}</div>`;
        },
      },
      visualMap: {
        type: "continuous",
        min,
        max,
        calculable: true,
        orient: "horizontal",
        left: 0,
        bottom: 0,
        itemWidth: 12,
        itemHeight: 120,
        inRange: { color: SEQUENTIAL_BLUES },
        textStyle: { color: CHART_INK.secondary, fontSize: 11 },
        formatter: (v) => formatValue(Number(v), unitCode),
      },
      series: [
        {
          type: "map",
          map: `nepal-${level}`,
          nameProperty: MAPS[level].nameProperty,
          roam: true,
          scaleLimit: { min: 1, max: 6 },
          selectedMode: false,
          itemStyle: {
            areaColor: "#f1efe9", // regions with no data recede to the wash
            borderColor: "#ffffff",
            borderWidth: 1,
          },
          emphasis: {
            label: { show: false },
            itemStyle: {
              areaColor: undefined,
              borderColor: "#1b2436",
              borderWidth: 1.4,
            },
          },
          label: { show: false },
          data: data.map((d) => ({ name: d.code, value: d.value })),
        },
      ],
    };
    chart.current.setOption(option, { notMerge: true });
  }, [mapReady, level, data, unitCode]);

  return (
    <div
      ref={holder}
      style={{ height: 500, width: "100%" }}
      role="img"
      aria-label={`Map of Nepal with each ${level} shaded by value. The same data is available in the table below.`}
    />
  );
}
