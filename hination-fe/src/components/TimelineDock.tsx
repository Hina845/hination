"use client";

import { Pause, Play } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

import { DANGEROUS_LEVEL, VI_WEEKDAYS } from "@/components/map-theme";
import type { ForecastDay } from "@/types/forecast";

export default function TimelineDock({
  days,
  selected,
  onSelect,
  peakLabel,
  dangerous,
}: {
  days: ForecastDay[];
  selected: number;
  onSelect: (index: number) => void;
  peakLabel?: string | null;
  dangerous?: boolean;
}) {
  const [playing, setPlaying] = useState(false);
  const progress = days.length > 0 ? ((selected + 1) / days.length) * 100 : 0;
  const tipLeft = days.length > 0 ? ((selected + 0.5) / days.length) * 100 : 0;

  useEffect(() => {
    if (!playing) return;
    const timer = window.setTimeout(() => {
      const next = selected + 1;
      onSelect(next);
      if (next >= days.length - 1) setPlaying(false);
    }, 3000);
    return () => window.clearTimeout(timer);
  }, [days.length, onSelect, playing, selected]);

  function togglePlayback() {
    if (playing) {
      setPlaying(false);
      return;
    }
    if (selected === days.length - 1) onSelect(0);
    setPlaying(true);
  }

  return (
    <div className="timeline-dock" aria-label="Dòng thời gian dự báo">
      <button className="play-button" type="button" onClick={togglePlayback} aria-label={playing ? "Tạm dừng" : "Phát dự báo"}>
        {playing ? <Pause weight="fill" /> : <Play weight="fill" />}
      </button>
      <div className="timeline-panel">
        {peakLabel && (
          <div
            className={`timeline-tip${dangerous ? " timeline-tip--danger" : ""}`}
            style={{ left: `${tipLeft}%` }}
            role="status"
            aria-live="polite"
          >
            {peakLabel}
          </div>
        )}
        <div className="timeline-progress" role="progressbar" aria-label="Tiến độ dự báo" aria-valuemin={1} aria-valuemax={days.length} aria-valuenow={selected + 1}>
          <span style={{ width: `${progress}%` }} />
        </div>
        <div className="timeline-days" role="tablist" aria-label="Chọn ngày dự báo">
          {days.map((day, index) => {
            const date = new Date(`${day.date}T00:00:00+07:00`);
            const weekday = VI_WEEKDAYS[date.getDay()];
            const dayOfMonth = date.getDate();
            const month = String(date.getMonth() + 1).padStart(2, "0");
            const isDangerous = day.maximumAlertLevel >= DANGEROUS_LEVEL;
            return (
              <button
                key={day.date}
                type="button"
                role="tab"
                aria-selected={selected === index}
                aria-label={`${weekday} ${dayOfMonth} tháng ${month}, cảnh báo cấp ${day.maximumAlertLevel}${isDangerous ? " (nguy hiểm)" : ""}`}
                className={`day-button${isDangerous ? " day-button--danger" : ""}`}
                onClick={() => onSelect(index)}
              >
                <span className="day-weekday">{weekday}</span>
                <span className="day-date">{dayOfMonth}</span>
                {isDangerous && <span className="day-danger-dot" aria-hidden />}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
