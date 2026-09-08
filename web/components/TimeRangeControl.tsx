"use client";

// Choosing a window in time (DIS.S2).
//
// The portal's first time control. Every other date choice here is a dropdown
// that swaps one chart for another; this scrubs a range, because the question
// this data answers — "when do landslides happen?" — is about a span, not a
// point.
//
// Two sliders rather than a fancy brush: a range input is keyboard-operable and
// screen-reader-labelled for free, where a custom drag handle is neither.

import { useId } from "react";

export interface YearRange {
  from: number;
  to: number;
}

export default function TimeRangeControl({
  min,
  max,
  value,
  onChange,
  presets,
}: {
  min: number;
  max: number;
  value: YearRange;
  onChange: (next: YearRange) => void;
  /** Optional shortcuts, e.g. "This monsoon" or "Since 2015". */
  presets?: { label: string; range: YearRange }[];
}) {
  const fromId = useId();
  const toId = useId();

  // The handles cannot cross: dragging "from" past "to" pushes the other along
  // rather than producing a window that ends before it starts, which the API
  // would reject anyway.
  const setFrom = (year: number) =>
    onChange({ from: year, to: Math.max(year, value.to) });
  const setTo = (year: number) =>
    onChange({ from: Math.min(year, value.from), to: year });

  return (
    <div className="time-range">
      <div className="time-range-head">
        <span className="time-range-label">
          {value.from === value.to ? value.from : `${value.from} – ${value.to}`}
        </span>
        {presets && presets.length > 0 && (
          <div className="time-range-presets">
            {presets.map((preset) => {
              const active =
                preset.range.from === value.from && preset.range.to === value.to;
              return (
                <button
                  key={preset.label}
                  type="button"
                  className={`btn ghost small${active ? " active" : ""}`}
                  aria-pressed={active}
                  onClick={() => onChange(preset.range)}
                >
                  {preset.label}
                </button>
              );
            })}
          </div>
        )}
      </div>
      <div className="time-range-sliders">
        <label className="sr-only" htmlFor={fromId}>
          Earliest year
        </label>
        <input
          id={fromId}
          type="range"
          min={min}
          max={max}
          step={1}
          value={value.from}
          onChange={(event) => setFrom(Number(event.target.value))}
        />
        <label className="sr-only" htmlFor={toId}>
          Latest year
        </label>
        <input
          id={toId}
          type="range"
          min={min}
          max={max}
          step={1}
          value={value.to}
          onChange={(event) => setTo(Number(event.target.value))}
        />
      </div>
      <div className="time-range-scale" aria-hidden="true">
        <span>{min}</span>
        <span>{max}</span>
      </div>
    </div>
  );
}
