"use client";

import { CursorClick, Drop, Thermometer, Wind } from "@phosphor-icons/react";
import { useLayoutEffect, useRef } from "react";

import type { DailyWeather } from "@/types/forecast";

type Props = {
  name: string;
  anchor: { x: number; y: number; radius: number } | null;
  levelColor: string;
  levelLabel: string;
  forecastLine: string;
  weather: DailyWeather;
};

const EDGE = 8; // keep the tip this far from the viewport edges

// Lightweight hover preview: just the headline numbers (danger level, temp, rain, wind)
// plus a "click to expand" nudge toward the full pinned brief. Non-interactive
// (pointer-events: none) so it never gets in the way of clicking the area beneath it.
export default function AreaHoverTip({ name, anchor, levelColor, levelLabel, forecastLine, weather }: Props) {
  const tipRef = useRef<HTMLDivElement>(null);

  // Place the tip beside the hovered marker: to its right, flipping left when it would
  // overflow, and clamped vertically — mirroring how the pinned brief used to float.
  useLayoutEffect(() => {
    const el = tipRef.current;
    if (!el) return;
    if (!anchor) {
      el.style.left = "";
      el.style.top = "";
      return;
    }
    const rect = el.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const gap = anchor.radius + 14;
    let left = anchor.x + gap;
    if (left + rect.width > vw - EDGE) left = anchor.x - gap - rect.width;
    left = Math.max(EDGE, Math.min(left, vw - rect.width - EDGE));
    let top = anchor.y - rect.height / 2;
    top = Math.max(EDGE, Math.min(top, vh - rect.height - EDGE));
    el.style.left = `${left}px`;
    el.style.top = `${top}px`;
  }, [anchor]);

  return (
    <div ref={tipRef} className="area-tip" role="tooltip">
      <div className="area-tip__head">
        <span className="area-tip__name">{name}</span>
        <span className="area-tip__chip" style={{ backgroundColor: levelColor }}>
          {levelLabel}
        </span>
      </div>
      <p className="area-tip__line">{forecastLine}</p>
      <ul className="area-tip__stats">
        <li><Thermometer weight="fill" /> {weather.temperatureMinC}–{weather.temperatureMaxC}°C</li>
        <li><Drop weight="fill" /> {weather.rainfallTotalMm} mm</li>
        <li><Wind weight="fill" /> {weather.windGustMaxKmh} km/h</li>
      </ul>
      <p className="area-tip__hint">
        <CursorClick weight="fill" /> Nhấn để xem chi tiết
      </p>
    </div>
  );
}
