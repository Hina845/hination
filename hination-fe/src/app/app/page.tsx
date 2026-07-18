import { redirect } from "next/navigation";

import ForecastMapShell from "@/components/ForecastMapShell";
import { readPredictLevelsForDate } from "@/lib/area-brief";
import { getSessionUser } from "@/lib/auth";
import { overallLevel } from "@/lib/danger-score";
import type { DangerLevel, ForecastResponse } from "@/types/forecast";

async function getForecast(): Promise<ForecastResponse | null> {
  const baseUrl = process.env.HINATION_API_BASE_URL ?? "http://127.0.0.1:8000";
  try {
    const response = await fetch(`${baseUrl}/api/v1/forecasts/latest`, { cache: "no-store" });
    if (!response.ok) return null;
    return (await response.json()) as ForecastResponse;
  } catch {
    return null;
  }
}

// Fold each area's warmed AI prediction into a combined "overall" level so the map
// renders reduced-API + news scoring immediately. Areas without a warmed brief fall
// back to (API − 1). Also recomputes each day's max alert level from the overall values.
//
// The news brief is warmed only for the current day (day 0) and its predictLevel is a
// "right now" signal, not a per-day one. So we read day 0's levels once as a base and
// reuse them across the whole 7-day horizon — otherwise days 1-6 would always show
// predictLevel 0 and the news signal would never move those days. A day that happens to
// have its own warmed row still wins.
function applyOverallLevels(forecast: ForecastResponse): ForecastResponse {
  const warmedDate = forecast.days[0]?.date.slice(0, 10);
  const basePredicts = warmedDate ? readPredictLevelsForDate(warmedDate) : new Map<string, number>();

  return {
    ...forecast,
    days: forecast.days.map((day) => {
      const dayPredicts = readPredictLevelsForDate(day.date.slice(0, 10));
      let maxOverall = 0;
      const areas = day.areas.map((area) => {
        const predictLevel = dayPredicts.get(area.id) ?? basePredicts.get(area.id) ?? 0;
        const overall = overallLevel(area.danger.level, predictLevel);
        maxOverall = Math.max(maxOverall, overall);
        return { ...area, danger: { ...area.danger, overallLevel: overall, predictLevel } };
      });
      return { ...day, areas, maximumAlertLevel: Math.max(1, maxOverall) as DangerLevel };
    }),
  };
}

export default async function AppPage() {
  const user = await getSessionUser();

  if (!user) {
    redirect("/login");
  }

  const forecast = await getForecast();
  if (!forecast) {
    return (
      <main className="forecast-unavailable">
        <span>DB–MWAI</span>
        <h1>Chưa thể tải dữ liệu dự báo</h1>
        <p>Hệ thống vẫn giữ an toàn cho phiên đăng nhập. Vui lòng thử lại khi dịch vụ dự báo hoạt động.</p>
      </main>
    );
  }

  // Use `||` (not `??`) so an env var that is defined-but-empty — e.g. docker-compose's
  // `${HINATION_TILE_URL:-}` expanding to "" — still falls back to the OSM default.
  return <ForecastMapShell forecast={applyOverallLevels(forecast)} tileUrl={process.env.HINATION_TILE_URL || "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"} />;
}
