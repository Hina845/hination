"use client";

import { Pause, Play } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

import type { ForecastDay } from "@/types/forecast";

const WEEKDAYS = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];

export default function TimelineDock({ days, selected, onSelect }: { days: ForecastDay[]; selected: number; onSelect: (index: number) => void }) {
  const [playing, setPlaying] = useState(false);
  const progress = days.length > 0 ? ((selected + 1) / days.length) * 100 : 0;

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
        <div className="timeline-progress" role="progressbar" aria-label="Tiến độ dự báo" aria-valuemin={1} aria-valuemax={days.length} aria-valuenow={selected + 1}>
          <span style={{ width: `${progress}%` }} />
        </div>
        <div className="timeline-days" role="tablist" aria-label="Chọn ngày dự báo">
          {days.map((day, index) => {
            const date = new Date(`${day.date}T00:00:00+07:00`);
            const weekday = WEEKDAYS[date.getDay()];
            const dayOfMonth = date.toLocaleDateString("vi-VN", { day: "2-digit" });
            return (
              <button
                key={day.date}
                type="button"
                role="tab"
                aria-selected={selected === index}
                aria-label={`${weekday} ${dayOfMonth}-${date.toLocaleDateString("vi-VN", { month: "2-digit" })}, cảnh báo cấp ${day.maximumAlertLevel}`}
                className="day-button"
                onClick={() => onSelect(index)}
              >
                <span className="day-weekday">{weekday}</span>
                <span className="day-date">{dayOfMonth}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
