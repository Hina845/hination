"use client";

import { ArrowClockwise, ArrowSquareOut, Drop, Sparkle, Thermometer, Warning, Wind, X } from "@phosphor-icons/react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { fetchLiveWeather, weatherCodeLabel, type LiveWeather } from "@/lib/live-weather";
import type { AreaBrief, AreaBriefInput } from "@/types/area-brief";
import type { Coordinates, DailyWeather } from "@/types/forecast";

// Module-level cache so re-hovering the same area+day is instant and never re-hits
// the API. The server already caches across accounts; this just avoids client churn.
const briefCache = new Map<string, AreaBrief>();
const cacheKeyFor = (areaId: string, date: string) => `${areaId}|${date}`;

type Props = {
  input: AreaBriefInput;
  anchor: { x: number; y: number; radius: number } | null;
  levelColor: string;
  levelLabel: string;
  // Weather shown in the merged card: the headline forecast line, the pre-computed daily
  // aggregate (fallback while live data loads / on error), and the point to fetch live data for.
  forecastLine: string;
  weather: DailyWeather;
  coordinates: Coordinates;
  onClose: () => void;
  onPointerEnter: () => void;
  onPointerLeave: () => void;
};

const EDGE = 8; // keep the card this far from the viewport edges

// Today in the province's local time (UTC+7); en-CA renders as YYYY-MM-DD to match forecast dates.
function localToday(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Bangkok" }).format(new Date());
}

function formatClock(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Bangkok" }).format(date);
}

function formatUpdated(generatedAt: number) {
  const time = new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit" }).format(new Date(generatedAt));
  const minutes = Math.round((Date.now() - generatedAt) / 60000);
  if (minutes < 1) return `${time} · vừa xong`;
  if (minutes < 60) return `${time} · ${minutes} phút trước`;
  const hours = Math.round(minutes / 60);
  return `${time} · ${hours} giờ trước`;
}

export default function AreaBriefCard({ input, anchor, levelColor, levelLabel, forecastLine, weather, coordinates, onClose, onPointerEnter, onPointerLeave }: Props) {
  const cacheKey = cacheKeyFor(input.areaId, input.date);
  const [brief, setBrief] = useState<AreaBrief | null>(() => briefCache.get(cacheKey) ?? null);
  const [loading, setLoading] = useState(!briefCache.has(cacheKey));
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState<LiveWeather | null>(null);
  const requestRef = useRef(0);
  const cardRef = useRef<HTMLElement>(null);

  const isToday = input.date === localToday();

  // Pull the accurate live reading for the hovered point from Open-Meteo (free, no key).
  // Silently ignore failures — the card still renders the pre-computed forecast aggregate.
  useEffect(() => {
    const controller = new AbortController();
    setLive(null);
    fetchLiveWeather(coordinates.lat, coordinates.lng, input.date, controller.signal)
      .then((data) => setLive(data))
      .catch(() => {});
    return () => controller.abort();
  }, [coordinates.lat, coordinates.lng, input.date]);

  // Prefer the live daily aggregate; fall back to the server's pre-computed values while it loads.
  const daily = live?.daily;
  const tMin = daily?.temperatureMinC ?? weather.temperatureMinC;
  const tMax = daily?.temperatureMaxC ?? weather.temperatureMaxC;
  const rain = daily?.rainfallTotalMm ?? weather.rainfallTotalMm;
  const gust = daily?.windGustMaxKmh ?? weather.windGustMaxKmh;
  const current = isToday ? live?.current ?? null : null;

  // Place the card beside the hovered marker: to its right, flipping left when it
  // would overflow, and clamped vertically. Recomputed when the anchor moves or the
  // content resizes (loading → loaded). We write straight to the element's style —
  // this is a DOM sync, not React state — and defer to the CSS layout on narrow screens.
  useLayoutEffect(() => {
    const el = cardRef.current;
    if (!el) return;
    if (!anchor || window.innerWidth <= 520) {
      el.style.left = "";
      el.style.top = "";
      el.style.right = "";
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
    el.style.right = "auto";
  }, [anchor, brief, loading, error]);

  const load = useCallback(
    async (refresh: boolean) => {
      const token = ++requestRef.current;
      setLoading(true);
      setError(null);
      try {
        const response = await fetch("/api/areas/brief", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...input, refresh }),
        });
        if (!response.ok) {
          const data = (await response.json().catch(() => ({}))) as { error?: string };
          throw new Error(data.error ?? `Lỗi ${response.status}`);
        }
        const data = (await response.json()) as AreaBrief;
        if (token !== requestRef.current) return;
        briefCache.set(cacheKey, data);
        setBrief(data);
      } catch (caught) {
        if (token !== requestRef.current) return;
        setError(caught instanceof Error ? caught.message : "Không thể tải bản tin");
      } finally {
        if (token === requestRef.current) setLoading(false);
      }
    },
    [cacheKey, input],
  );

  // Fetch once per area+day when the card opens, with a short debounce so a quick
  // mouse pass-over doesn't trigger a generation. The card is keyed per area+day in
  // the parent, so a cached entry is already picked up by the initial state above and
  // this effect only runs the network request when nothing is cached yet.
  useEffect(() => {
    if (briefCache.has(cacheKey)) return;
    const timer = setTimeout(() => load(false), 300);
    return () => clearTimeout(timer);
  }, [cacheKey, load]);

  return (
    <aside
      ref={cardRef}
      className="area-brief"
      aria-label={`Bản tin AI cho ${input.name}`}
      onMouseEnter={onPointerEnter}
      onMouseLeave={onPointerLeave}
    >
      <header className="area-brief__head">
        <div className="area-brief__title">
          <h3>{input.name}</h3>
          <span className="area-brief__chip" style={{ backgroundColor: levelColor }}>
            {levelLabel}
          </span>
        </div>
        <button type="button" className="area-brief__close" aria-label="Đóng" onClick={onClose}>
          <X />
        </button>
      </header>

      <div className="area-brief__weather">
        <p className="area-brief__forecast-line">{forecastLine}</p>
        <ul className="area-brief__stats">
          <li><Thermometer weight="fill" /> {tMin}–{tMax}°C</li>
          <li><Drop weight="fill" /> {rain} mm</li>
          <li><Wind weight="fill" /> {gust} km/h</li>
        </ul>
      </div>

      <div className="area-brief__ai">
        <div className="area-brief__ai-head">
          <Sparkle weight="fill" /> Tóm tắt AI · việc cần làm
        </div>
        {loading && !brief ? (
          <div className="area-brief__loading">
            <span className="area-brief__spinner" aria-hidden />
            Đang tổng hợp bản tin mới nhất…
          </div>
        ) : error && !brief ? (
          <div className="area-brief__error">
            <Warning weight="fill" /> {error}
            <button type="button" onClick={() => load(true)}>
              Thử lại
            </button>
          </div>
        ) : brief ? (
          <>
            <p className="area-brief__headline">{brief.headline}</p>
            <p className="area-brief__summary">{brief.summary}</p>
          </>
        ) : null}
      </div>

      {brief && (
        <div className="area-brief__meta">
          <span className="area-brief__updated">Cập nhật {formatUpdated(brief.generatedAt)}</span>
          <button
            type="button"
            className="area-brief__refresh"
            onClick={() => load(true)}
            disabled={loading}
            title="Lấy bản tin mới nhất"
          >
            <ArrowClockwise className={loading ? "spin" : undefined} /> Làm mới
          </button>
        </div>
      )}

      {brief && brief.sources.length > 0 && (
        <div className="area-brief__sources">
          <span className="area-brief__sources-label">Nguồn tin</span>
          <ul>
            {brief.sources.slice(0, 5).map((source) => (
              <li key={source.url}>
                <a href={source.url} target="_blank" rel="noopener noreferrer" className="area-brief__source">
                  <ArrowSquareOut />
                  <span className="area-brief__source-title">{source.title}</span>
                  <span className="area-brief__source-meta">
                    {source.publisher}
                    {source.age ? ` · ${source.age}` : ""}
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}

      {brief && brief.sources.length === 0 && !loading && (
        <p className="area-brief__no-sources">Chưa tìm thấy bản tin liên quan gần đây.</p>
      )}
    </aside>
  );
}
