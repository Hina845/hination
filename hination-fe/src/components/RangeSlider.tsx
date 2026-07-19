"use client";

import { useCallback } from "react";

// Dual-thumb range slider over an integer scale, used to pick a danger-level band for the
// "send to dangerous areas" blast. Two overlaid native range inputs (so keyboard + a11y
// come free); the thumbs clamp against each other so min never crosses max. The colored
// fill between the thumbs is a positioned div — the tracks themselves are transparent.
export default function RangeSlider({
  min,
  max,
  value,
  onChange,
  ariaLabelMin = "Mức tối thiểu",
  ariaLabelMax = "Mức tối đa",
}: {
  min: number;
  max: number;
  value: [number, number];
  onChange: (next: [number, number]) => void;
  ariaLabelMin?: string;
  ariaLabelMax?: string;
}) {
  const [low, high] = value;
  const span = Math.max(1, max - min);
  const lowPct = ((low - min) / span) * 100;
  const highPct = ((high - min) / span) * 100;

  const setLow = useCallback(
    (raw: number) => onChange([Math.min(raw, high), high]),
    [high, onChange],
  );
  const setHigh = useCallback(
    (raw: number) => onChange([low, Math.max(raw, low)]),
    [low, onChange],
  );

  return (
    <div className="range-slider">
      <div className="range-slider__track" aria-hidden />
      <div
        className="range-slider__fill"
        style={{ left: `${lowPct}%`, right: `${100 - highPct}%` }}
        aria-hidden
      />
      <input
        type="range"
        min={min}
        max={max}
        step={1}
        value={low}
        aria-label={ariaLabelMin}
        onChange={(event) => setLow(Number(event.target.value))}
        className="range-slider__input"
      />
      <input
        type="range"
        min={min}
        max={max}
        step={1}
        value={high}
        aria-label={ariaLabelMax}
        onChange={(event) => setHigh(Number(event.target.value))}
        className="range-slider__input"
      />
    </div>
  );
}
