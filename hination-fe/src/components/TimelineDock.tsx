"use client";

import { ClockCounterClockwise, Pause, Play } from "@phosphor-icons/react";
import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

import { DANGEROUS_LEVEL, VI_WEEKDAYS } from "@/components/map-theme";
import type { ForecastDay } from "@/types/forecast";

export default function TimelineDock({
  days,
  dayLevels,
  selected,
  onSelect,
  slotsPerDay = 6,
  selectedIndex,
  onSelectIndex,
  selectedFraction,
  selectedLabel,
  nowIndex,
  nowFraction,
}: {
  days: ForecastDay[];
  // Alert level per day — drives the danger styling/dot on each day label.
  dayLevels?: number[];
  selected: number;
  onSelect: (index: number) => void;
  // Continuous week scrubber (Windy-style). The handle drags across the whole horizon and
  // snaps to `slotsPerDay` slots per day; `selectedIndex` is the flat slot it lands on.
  // `selectedFraction` (0..1) positions the handle; `selectedLabel` is the floating tooltip.
  // Omit `onSelectIndex` to render the plain day-tab fallback.
  slotsPerDay?: number;
  selectedIndex?: number;
  onSelectIndex?: (index: number) => void;
  selectedFraction?: number;
  selectedLabel?: string | null;
  // Flat slot index + track fraction of "now"; a marker on the track jumps here.
  nowIndex?: number;
  nowFraction?: number | null;
}) {
  const [playing, setPlaying] = useState(false);
  const trackRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  const progress = days.length > 0 ? ((selected + 1) / days.length) * 100 : 0;

  const showSlider = onSelectIndex !== undefined && selectedIndex !== undefined;
  const totalSlots = days.length * slotsPerDay;
  const fraction = Math.min(1, Math.max(0, selectedFraction ?? 0));

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

  // Pointer x → the flat slot under it (each slot is a fixed 24/slotsPerDay-hour window).
  function slotAt(clientX: number): number {
    const track = trackRef.current;
    if (!track) return selectedIndex ?? 0;
    const rect = track.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    return Math.min(totalSlots - 1, Math.floor(ratio * totalSlots));
  }

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    if (!showSlider) return;
    event.preventDefault();
    dragging.current = true;
    trackRef.current?.setPointerCapture(event.pointerId);
    onSelectIndex(slotAt(event.clientX));
  }
  function onPointerMove(event: PointerEvent<HTMLDivElement>) {
    if (!dragging.current || !showSlider) return;
    onSelectIndex(slotAt(event.clientX));
  }
  function endDrag(event: PointerEvent<HTMLDivElement>) {
    dragging.current = false;
    trackRef.current?.releasePointerCapture?.(event.pointerId);
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (!showSlider) return;
    const index = selectedIndex ?? 0;
    if (event.key === "ArrowRight" || event.key === "ArrowUp") {
      event.preventDefault();
      onSelectIndex(Math.min(totalSlots - 1, index + 1));
    } else if (event.key === "ArrowLeft" || event.key === "ArrowDown") {
      event.preventDefault();
      onSelectIndex(Math.max(0, index - 1));
    } else if (event.key === "Home") {
      event.preventDefault();
      onSelectIndex(0);
    } else if (event.key === "End") {
      event.preventDefault();
      onSelectIndex(totalSlots - 1);
    } else if (event.key === "PageUp") {
      event.preventDefault();
      onSelectIndex(Math.min(totalSlots - 1, index + slotsPerDay));
    } else if (event.key === "PageDown") {
      event.preventDefault();
      onSelectIndex(Math.max(0, index - slotsPerDay));
    }
  }

  return (
    <div className="timeline-dock" aria-label="Dòng thời gian dự báo">
      {showSlider && nowIndex !== undefined && nowIndex >= 0 && (
        <button
          className="now-button"
          type="button"
          onClick={() => onSelectIndex(nowIndex)}
          aria-label="Đặt lại về hiện tại"
          title="Đặt lại về hiện tại"
        >
          <ClockCounterClockwise weight="bold" />
        </button>
      )}
      <button className="play-button" type="button" onClick={togglePlayback} aria-label={playing ? "Tạm dừng" : "Phát dự báo"}>
        {playing ? <Pause weight="fill" /> : <Play weight="fill" />}
      </button>
      <div className={`timeline-panel${showSlider ? " timeline-panel--slider" : ""}`}>
        {showSlider ? (
          <>
            <div
              className="timeline-track"
              ref={trackRef}
              role="slider"
              tabIndex={0}
              aria-label="Chọn thời điểm dự báo"
              aria-valuemin={0}
              aria-valuemax={totalSlots - 1}
              aria-valuenow={selectedIndex}
              aria-valuetext={selectedLabel ?? undefined}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={endDrag}
              onPointerCancel={endDrag}
              onKeyDown={onKeyDown}
            >
              <span className="timeline-fill" style={{ width: `${fraction * 100}%` }} />
              {nowFraction != null && (
                <button
                  type="button"
                  className="timeline-now-mark"
                  style={{ left: `${Math.min(1, Math.max(0, nowFraction)) * 100}%` }}
                  aria-label="Về thời điểm hiện tại"
                  title="Bây giờ"
                  onPointerDown={(event) => event.stopPropagation()}
                  onClick={(event) => {
                    event.stopPropagation();
                    if (nowIndex !== undefined && nowIndex >= 0) onSelectIndex(nowIndex);
                  }}
                />
              )}
              <span className="timeline-handle" style={{ left: `${fraction * 100}%` }}>
                {selectedLabel && <span className="timeline-bubble">{selectedLabel}</span>}
              </span>
            </div>
            <div className="timeline-daybar">
              {days.map((day, index) => {
                const date = new Date(`${day.date}T00:00:00+07:00`);
                const weekday = VI_WEEKDAYS[date.getDay()];
                const dayOfMonth = date.getDate();
                const month = String(date.getMonth() + 1).padStart(2, "0");
                const level = dayLevels?.[index] ?? day.maximumAlertLevel;
                const isDangerous = level >= DANGEROUS_LEVEL;
                return (
                  <button
                    key={day.date}
                    type="button"
                    className={`timeline-dayseg${selected === index ? " timeline-dayseg--active" : ""}${isDangerous ? " timeline-dayseg--danger" : ""}`}
                    aria-label={`${weekday} ${dayOfMonth} tháng ${month}, cảnh báo cấp ${level}${isDangerous ? " (nguy hiểm)" : ""}`}
                    aria-pressed={selected === index}
                    onClick={() => onSelect(index)}
                    tabIndex={-1}
                  >
                    <span className="timeline-dayseg__label">{weekday} {dayOfMonth}</span>
                    {isDangerous && <span className="day-danger-dot" aria-hidden />}
                  </button>
                );
              })}
            </div>
          </>
        ) : (
          <>
            <div className="timeline-progress" role="progressbar" aria-label="Tiến độ dự báo" aria-valuemin={1} aria-valuemax={days.length} aria-valuenow={selected + 1}>
              <span style={{ width: `${progress}%` }} />
            </div>
            <div className="timeline-days" role="tablist" aria-label="Chọn ngày dự báo">
              {days.map((day, index) => {
                const date = new Date(`${day.date}T00:00:00+07:00`);
                const weekday = VI_WEEKDAYS[date.getDay()];
                const dayOfMonth = date.getDate();
                const month = String(date.getMonth() + 1).padStart(2, "0");
                const level = dayLevels?.[index] ?? day.maximumAlertLevel;
                const isDangerous = level >= DANGEROUS_LEVEL;
                return (
                  <button
                    key={day.date}
                    type="button"
                    role="tab"
                    aria-selected={selected === index}
                    aria-label={`${weekday} ${dayOfMonth} tháng ${month}, cảnh báo cấp ${level}${isDangerous ? " (nguy hiểm)" : ""}`}
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
          </>
        )}
      </div>
    </div>
  );
}
