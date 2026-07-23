"use client";

// The landing hero: Nepal at the center, the 8 sectors orbiting as nodes, each
// carrying one live number and doubling as navigation (P2B.S6). CSS-only
// rotor/counter-rotor motion (nodes drift, text stays upright); pauses on hover
// or focus; fully off under prefers-reduced-motion; reflows to a static grid on
// phones. Zero new dependencies.

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchSeries } from "@/lib/api";
import { formatCompact, formatValue } from "@/lib/format";
import { latestPair } from "@/lib/latest";
import { SECTORS } from "@/lib/sectors";

// Nepal silhouette — generated once from web/public/maps/nepal-provinces.json
// (the official 2020 outline) via mapshaper `-dissolve2 -simplify 6%`.
const NEPAL_VIEWBOX = "0 0 800 405";
const NEPAL_PATH = "M 633.8 247.61 635.85 238.38 639.56 232.28 645.48 236.43 650.8 232.71 655.62 233.19 660.7 241.5 666.97 240.6 676.32 247.59 685.11 248.22 691.81 255.71 692.63 259 700.21 261 707.26 257.98 712.41 260.36 716.62 260.13 722.35 257.02 727.9 259.06 737.99 256.88 741.15 261.89 752.36 262.43 758.29 253.12 763.02 248.1 766.13 252.11 772.47 251.4 777.64 254.37 781.95 252.63 788.19 255.96 793.86 255.44 799 259.29 796.78 268.15 794.8 268.75 793.44 276.12 787.61 283.52 783.59 294.47 786.98 299.01 783.37 305.08 785.79 308.4 782.38 313.31 779.96 327.32 778.41 328.54 782.96 337.77 786.86 337.88 790.86 342.59 792.64 351.28 796.16 354.24 797.7 363.72 795.26 376.04 790.27 383.35 788.66 396.28 780.02 403.96 778.45 400.88 772.55 398.35 769.48 392.56 764.44 396.57 758.59 393.37 756.21 399.14 750.97 397.47 745.16 400.78 738.84 400.85 731.88 397.12 727 396.19 719.35 398.29 711.88 402.95 707.33 402.71 705.44 398.75 697.19 399.76 690.24 395.22 688.39 386.24 674.67 388.71 671.87 391.49 670.89 394.05 664.95 396.33 658.37 394.34 655.86 397.75 639.16 390.69 636.37 386.58 613.44 378.59 607.88 379.06 604.56 381.69 598.47 379.58 590.12 374.96 580.93 374.85 578.92 377.52 569.56 383.47 557.03 375.26 556.41 368.7 557.24 361.35 555.95 358.98 546.37 353.74 538.43 357.27 533.83 361.22 529.53 362.76 525.23 361.8 518.04 366.68 504.62 363.93 502.59 360 503.88 354.08 496.17 353.85 493.56 355.56 488.1 353.61 481.6 345.24 471.43 342.53 467.31 339.32 465.06 341.75 450.27 336.8 454.26 327.27 454.84 319.44 448.3 308.47 434.88 306.22 421.38 304.68 414.28 302.04 412.18 297.04 404.09 294.73 397.53 290.33 392.34 297.97 388.82 298.74 380.53 297.29 377.03 298.44 374.46 299.24 376.55 305.91 370.61 305.06 349.53 295.34 327.38 294.34 329.19 300.67 325.94 306.2 322.35 308.73 318.12 308.53 315.96 303.76 305.39 296.49 292.61 297.36 284.78 295.49 282.35 292.23 263.37 292.09 265.25 283.59 261.39 276 260.46 271.44 250.57 272.16 244.31 274.14 235.25 274.84 230.65 272.48 227.26 268.57 221.05 265.63 211.71 258.74 203.36 256.57 198.23 250.93 188.16 250.31 183.94 255.55 180.04 257.36 172.14 252.76 161.71 244.5 156.33 243.95 140.15 235.26 140.7 231.75 136.97 227.54 130.04 226 129.66 229.39 124.7 230.23 124.69 224.01 116.08 215.03 113.91 208.01 99.87 204.69 93.25 198.86 91.22 200.78 72.16 191.48 70.53 187.92 65.3 187.7 59.09 181.22 55.21 180.7 48.17 175.66 44.61 178.15 46.4 186.83 41.5 185.5 40.4 182.43 35.91 180.71 32.15 181.77 22.52 173.79 19.83 169.08 16.44 169.32 6.85 162.12 1.62 161.29 1 153.54 7.7 144.76 9.43 135.25 13.37 131.89 18.32 133.68 22.01 131.29 20.55 126.99 24.42 125.21 26.46 115.49 22.72 111.42 19.38 101.58 24.92 100.95 24.28 97.54 28.72 95.37 35.28 86.96 36.09 81.61 33.66 80.3 31.14 73.91 36.04 67.38 43.53 67.41 49.51 61.73 53.61 51.97 61.71 51.39 67.65 47.39 74.29 38.54 81.38 34.37 80.67 31.61 69.91 19.97 69.65 17.77 60.83 13.83 54.69 1 64.66 6.19 71.29 11.51 73.89 15.26 79.8 16.27 88.59 20.6 96.4 22.92 97.73 29.76 101.42 32.85 102.2 42.04 105.41 45.37 114.58 46.64 119.92 42.92 121.16 35.94 118.56 32.53 126.01 31.64 132.12 26.88 131.52 24.46 134.75 17.46 132.22 11.03 133.28 6.08 141.07 9.92 146.83 10.89 148.61 5.23 152.74 6.97 155.45 3.76 166.88 9.26 185.31 13.31 191.09 15.93 201.55 13.1 203.56 17.78 200.92 23.91 211.41 32.28 207.56 39.9 215.19 39.97 226.84 46.34 229.77 44.95 233.63 48.44 243.14 50.2 250.91 58.68 253.91 63.63 259.6 61.54 266.04 73.7 272.26 77.74 275.62 78.26 282.84 76.31 283.48 79.29 292.56 81.24 297.31 85.93 303.19 84.12 314.84 88.75 314.18 91.98 316.92 96.48 320.23 95.48 326.53 103.85 329.91 104.17 329.96 110.17 335.41 118.52 339.66 120.48 340.26 124.07 351.35 129.83 353.7 128.09 353.96 125.37 358.97 121.39 367.4 120.85 368.92 115.75 383.83 112.91 389.65 117.06 391.57 115.87 398.7 117.97 398.29 120.99 404.85 122.06 403.33 126.34 405.52 137.44 411.56 144.11 408.88 153.62 409.78 155.91 427.32 159.69 430.92 165.62 430.05 167.95 435.25 171.28 437.72 169.99 448.65 171.18 455.95 181.17 472.07 186.47 484.18 183.29 491.01 176.48 496.58 176.08 500.86 180.3 504.04 187.59 500.62 194.63 497.47 195.55 497.12 206.96 495.85 209.39 503.13 211.56 505.27 210.04 510.24 214.5 518.58 213.58 522.26 216.05 525.98 211.3 530.16 210.33 543.4 213.13 544.93 218.18 550.02 213.66 552.34 205.86 555 205.5 557.53 212.07 558.6 219.81 566.59 225.26 573.28 232.67 573.61 238.12 580.72 243.24 578.2 249.04 583.57 252.05 589.63 253.18 595.42 250.45 593.01 244.05 591.41 234.41 594.82 234.4 598.98 229.83 602.6 229.81 605.49 245.23 611.58 245.48 614.52 248.47 620.64 249.45 626.32 252.41 633.8 247.61 Z";

// Node anchors on an ellipse rx=46% ry=42%, θ_i = -90° + i·45°:
// left = 50% + rx·cosθ, top = 50% + ry·sinθ. Precomputed to avoid runtime trig.
// x/y are the same values as numbers, for the SVG connector line.
const NODE_POS: Array<{ left: string; top: string; x: number; y: number }> = [
  { left: "50%", top: "8%", x: 50, y: 8 }, // -90°
  { left: "82.5%", top: "20.3%", x: 82.5, y: 20.3 }, // -45°
  { left: "96%", top: "50%", x: 96, y: 50 }, // 0°
  { left: "82.5%", top: "79.7%", x: 82.5, y: 79.7 }, // 45°
  { left: "50%", top: "92%", x: 50, y: 92 }, // 90°
  { left: "17.5%", top: "79.7%", x: 17.5, y: 79.7 }, // 135°
  { left: "4%", top: "50%", x: 4, y: 50 }, // 180°
  { left: "17.5%", top: "20.3%", x: 17.5, y: 20.3 }, // 225°
];

interface NumValue {
  value: number;
  unit: string;
}

// Hero-glance formatting: one decimal, no false precision (detail lives on the
// sector pages). 6.7% not 6.73%; 70.6 not 70.64.
function fmt(v: number, unit: string): string {
  if (unit === "COUNT" || unit === "PERSONS") return formatCompact(v);
  if (unit === "PCT") return `${v.toFixed(1)}%`;
  if (unit === "USD") return formatValue(v, unit);
  return v.toFixed(1);
}

/** Count-up: animates 0 → value once on mount (instant under reduced-motion). */
function OrbitValue({ value, unit }: NumValue) {
  const [v, setV] = useState(0);
  useEffect(() => {
    const reduce =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setV(value);
      return;
    }
    let raf = 0;
    const start = performance.now();
    const dur = 900;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / dur);
      const eased = 1 - Math.pow(1 - t, 3);
      setV(value * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  return <>{fmt(v, unit)}</>;
}

export default function DataOrbit() {
  // orbitCode -> numeric latest value + unit
  const [data, setData] = useState<Record<string, NumValue>>({});
  // index of the hovered/focused node (drives the center reveal + connector)
  const [active, setActive] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    const codes = SECTORS.map((s) => s.orbitCode).filter(
      (c): c is string => Boolean(c),
    );
    Promise.allSettled(codes.map((c) => fetchSeries(c, "NP"))).then((results) => {
      if (cancelled) return;
      const map: Record<string, NumValue> = {};
      results.forEach((r, i) => {
        if (r.status !== "fulfilled") return;
        const pair = latestPair(r.value);
        if (!pair) return;
        map[codes[i]] = { value: pair.latest, unit: r.value.unit_code };
      });
      setData(map);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const activeSector = active !== null ? SECTORS[active] : null;
  const activeEntry = activeSector?.orbitCode ? data[activeSector.orbitCode] : undefined;

  return (
    <div className={`orbit-wrap${active !== null ? " has-active" : ""}`}>
      <div className="orbit-ring" aria-hidden="true" />

      <div className="orbit-center" aria-hidden="true">
        <svg
          className="orbit-map"
          viewBox={NEPAL_VIEWBOX}
          role="img"
          aria-label="Outline of Nepal"
        >
          <path d={NEPAL_PATH} fill="var(--crimson)" fillOpacity="0.9" />
        </svg>
        <div className="orbit-caption">
          {activeSector ? (
            <>
              <p className="cap-label">{activeSector.titleShort}</p>
              <p className="cap-value">
                {activeEntry ? fmt(activeEntry.value, activeEntry.unit) : "in preparation"}
              </p>
              {activeEntry && activeSector.orbitLabel && (
                <p className="cap-metric">{activeSector.orbitLabel}</p>
              )}
            </>
          ) : (
            <>
              <p className="np">नेपाल</p>
              <p className="np-sub">Nepal in data</p>
            </>
          )}
        </div>
      </div>

      <div className="orbit-rotor">
        <svg
          className="orbit-connector"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          {active !== null && (
            <line
              className="conn-line"
              x1="50"
              y1="50"
              x2={NODE_POS[active].x}
              y2={NODE_POS[active].y}
            />
          )}
        </svg>

        {SECTORS.map((sector, i) => {
          const entry = sector.orbitCode ? data[sector.orbitCode] : undefined;
          return (
            <Link
              key={sector.slug}
              href={`/${sector.slug}`}
              className={`orbit-node${active === i ? " active" : ""}`}
              style={{ left: NODE_POS[i].left, top: NODE_POS[i].top }}
              aria-label={`${sector.title} — open sector`}
              onMouseEnter={() => setActive(i)}
              onMouseLeave={() => setActive((cur) => (cur === i ? null : cur))}
              onFocus={() => setActive(i)}
              onBlur={() => setActive((cur) => (cur === i ? null : cur))}
            >
              <span className="node-title">{sector.titleShort}</span>
              {sector.orbitCode ? (
                entry ? (
                  <>
                    <span className="node-value">
                      <OrbitValue value={entry.value} unit={entry.unit} />
                    </span>
                    {sector.orbitLabel && (
                      <span className="node-metric">{sector.orbitLabel}</span>
                    )}
                  </>
                ) : (
                  <span className="node-value skeleton" aria-hidden="true" />
                )
              ) : (
                <span className="node-value muted">in preparation</span>
              )}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
