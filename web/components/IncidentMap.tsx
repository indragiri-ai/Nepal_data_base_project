"use client";

// Individual disasters, as points on Nepal (DIS.S2).
//
// The portal's FIRST point map. Every other map here is a choropleth — a whole
// district shaded by one number. This draws one mark per recorded event, at the
// coordinate the government's own record gives it, which is the only honest way
// to show data that is about single things that happened rather than averages.
//
// A THIRD echarts wrapper, deliberately. `EChart.tsx` registers line and bar;
// `ChoroplethMap.tsx` registers map + visualMap. Neither should grow a scatter
// and a geo coordinate system it does not use, because every sector page pays
// for what its charts register. One wrapper per chart form is the convention
// here, and this is a new form.
//
// Boundaries are the same simplified files the choropleth draws
// (mesaugat/geoJSON-Nepal, MIT, OCHA P-codes), so a point that the ingestion
// placed inside a district lands inside that district's outline here too.

import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { ScatterChart, type ScatterSeriesOption } from "echarts/charts";
import {
  GeoComponent,
  type GeoComponentOption,
  TooltipComponent,
  type TooltipComponentOption,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { CHART_INK, TOOLTIP_STYLE } from "@/components/EChart";
import type { Incident } from "@/lib/api";

echarts.use([ScatterChart, GeoComponent, TooltipComponent, CanvasRenderer]);

const MAP_NAME = "nepal-districts-base";
const MAP_URL = "/maps/nepal-districts.json";

/** Escape text before it goes into a tooltip's HTML.
 *
 *  ECharts tooltip formatters return RAW HTML, so React's escaping does not
 *  apply. Incident titles come from an external system and are written by
 *  people filing reports — exactly the shape the 2026-09-06 security review
 *  flagged (finding 7) for the chart tooltips that already existed. Nothing
 *  reaches a tooltip here without passing through this. */
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

let mapRegistered = false;

async function ensureBaseMap(): Promise<void> {
  if (mapRegistered) return;
  const res = await fetch(MAP_URL);
  if (!res.ok) throw new Error(`Couldn't load the map of Nepal (HTTP ${res.status}).`);
  echarts.registerMap(MAP_NAME, await res.json());
  mapRegistered = true;
}

type Option = echarts.ComposeOption<
  ScatterSeriesOption | GeoComponentOption | TooltipComponentOption
>;

/** Marks are sized by how many people an event harmed, not by how "important"
 *  it looks. Deliberately a narrow range: a large dot must not turn a death
 *  into decoration, and a small one must stay clickable. */
function markSize(incident: Incident): number {
  const harmed =
    (incident.deaths ?? 0) + (incident.missing ?? 0) + (incident.injured ?? 0);
  if (harmed >= 10) return 16;
  if (harmed >= 3) return 12;
  if (harmed >= 1) return 9;
  return 6;
}

function describeHarm(incident: Incident): string {
  const parts: string[] = [];
  // A null count means the source published no figure; a zero means it counted
  // none. Only the figures that exist are shown, so the reader is never handed
  // a "0 dead" the government never said.
  if (incident.deaths) parts.push(`${incident.deaths} dead`);
  if (incident.missing) parts.push(`${incident.missing} missing`);
  if (incident.injured) parts.push(`${incident.injured} injured`);
  if (incident.affected_families) parts.push(`${incident.affected_families} families affected`);
  if (incident.houses_destroyed) parts.push(`${incident.houses_destroyed} homes destroyed`);
  return parts.join(" · ");
}

export interface HazardStyle {
  code: string;
  name: string;
  color: string | null;
}

export default function IncidentMap({
  incidents,
  hazards,
  onError,
  onSelect,
}: {
  incidents: Incident[];
  hazards: HazardStyle[];
  onError: (message: string) => void;
  onSelect?: (incident: Incident) => void;
}) {
  const holder = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const [ready, setReady] = useState(false);
  const selectRef = useRef(onSelect);
  selectRef.current = onSelect;

  // Only incidents with a coordinate can be drawn. The 1971-2013 archive has
  // none — those events are real and counted, they simply have no point, and
  // the caller is told how many are missing from the picture.
  const mappable = useMemo(
    () => incidents.filter((i) => i.lat !== null && i.lon !== null),
    [incidents],
  );

  const colorOf = useMemo(() => {
    const map = new Map(hazards.map((h) => [h.code, h.color ?? CHART_INK.secondary]));
    return (code: string) => map.get(code) ?? CHART_INK.secondary;
  }, [hazards]);

  useEffect(() => {
    const el = holder.current;
    if (!el) return;
    const instance = echarts.init(el);
    chart.current = instance;
    instance.on("click", (params: { data?: unknown }) => {
      const point = params.data as { incident?: Incident } | undefined;
      if (point?.incident && selectRef.current) selectRef.current(point.incident);
    });
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(el);
    return () => {
      observer.disconnect();
      instance.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    ensureBaseMap()
      .then(() => {
        if (!cancelled) setReady(true);
      })
      .catch((err) => {
        if (!cancelled) onError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [onError]);

  useEffect(() => {
    if (!ready || !chart.current) return;

    // One series per hazard, so the legend colours mean something and a reader
    // can pick out floods from fires without reading every tooltip.
    const byHazard = new Map<string, Incident[]>();
    for (const incident of mappable) {
      const list = byHazard.get(incident.hazard);
      if (list) list.push(incident);
      else byHazard.set(incident.hazard, [incident]);
    }

    const option: Option = {
      tooltip: {
        ...TOOLTIP_STYLE,
        trigger: "item",
        formatter: (params) => {
          const point = (params as unknown as { data?: { incident?: Incident } }).data;
          const incident = point?.incident;
          if (!incident) return "";
          const harm = describeHarm(incident);
          return `<div style="font-weight:650;max-width:280px">${escapeHtml(
            incident.title,
          )}</div>
            <div style="color:${CHART_INK.axisLabel};margin-top:2px">${escapeHtml(
              incident.incident_on,
            )} · ${escapeHtml(incident.hazard_name)} · ${escapeHtml(incident.geo_name)}</div>
            ${harm ? `<div style="font-weight:650;margin-top:4px">${escapeHtml(harm)}</div>` : ""}`;
        },
      },
      geo: {
        map: MAP_NAME,
        roam: true,
        scaleLimit: { min: 1, max: 12 },
        itemStyle: {
          // The country recedes; the events are the subject.
          areaColor: "#f4f2ec",
          borderColor: "#ffffff",
          borderWidth: 1,
        },
        emphasis: { itemStyle: { areaColor: "#ece9e1" }, label: { show: false } },
      },
      series: [...byHazard.entries()].map(([hazard, list]) => ({
        type: "scatter" as const,
        name: hazard,
        coordinateSystem: "geo" as const,
        data: list.map((incident) => ({
          value: [incident.lon as number, incident.lat as number],
          incident,
          symbolSize: markSize(incident),
        })),
        itemStyle: {
          color: colorOf(hazard),
          opacity: 0.72,
          borderColor: "#ffffff",
          borderWidth: 0.5,
        },
        emphasis: { itemStyle: { opacity: 1 } },
      })),
    };
    chart.current.setOption(option, true);
  }, [ready, mappable, colorOf]);

  const unmapped = incidents.length - mappable.length;

  return (
    <div className="incident-map">
      <div ref={holder} className="incident-map-canvas" role="img"
           aria-label={`Map of ${mappable.length} recorded incidents in Nepal`} />
      {unmapped > 0 && (
        <p className="incident-map-note">
          {unmapped.toLocaleString()} of these {incidents.length.toLocaleString()} records
          have no coordinate and are not drawn. They are counted in the figures and listed
          below.
        </p>
      )}
    </div>
  );
}
