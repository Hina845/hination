import ForecastMapShell from "@/components/ForecastMapShell";
import { readPredictLevelsForDate } from "@/lib/area-brief";
import { getSessionUser } from "@/lib/auth";
import { overallLevel } from "@/lib/danger-score";
import { getForecast } from "@/lib/forecast";
import { totalSmsSent } from "@/lib/sms-log";
import { countVillagers, countVillagersByArea } from "@/lib/villagers";
import type { DangerLevel, ForecastResponse } from "@/types/forecast";

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
        const predict = dayPredicts.get(area.id) ?? basePredicts.get(area.id);
        // No warmed brief for this area yet (fresh deploy while the warm runs, or the
        // Brave/OpenAI keys are unset): there's no news signal to calibrate against, so
        // show the raw model level rather than the reduced one. This keeps the map on the
        // real (varied) levels instead of collapsing every area to level−1 ("all low").
        // Once the brief warms, `predict` is defined and the intended reduce+news blend applies.
        const predictLevel = predict ?? 0;
        const overall = predict === undefined ? area.danger.level : overallLevel(area.danger.level, predict);
        maxOverall = Math.max(maxOverall, overall);
        // Apply the same reduce+news blend to every hour so the timeline scrubber colors
        // each hour consistently with the day-peak view (the AI predict signal is per-area,
        // not per-hour, so the same offset applies across the day's 24 hours).
        const hours = area.hours.map((hour) => ({
          ...hour,
          predictLevel,
          overallLevel: predict === undefined ? hour.level : overallLevel(hour.level, predict),
        }));
        return { ...area, hours, danger: { ...area.danger, overallLevel: overall, predictLevel } };
      });
      return { ...day, areas, maximumAlertLevel: Math.max(1, maxOverall) as DangerLevel };
    }),
  };
}

export default async function AppPage() {
  // Open dashboard: no login required to view the forecast map. Only /manage
  // (villager list) is gated, which is the village chief's optional login.
  const forecast = await getForecast();
  if (!forecast) {
    return (
      <main className="forecast-unavailable">
        <span>Điện Biên Forecast</span>
        <h1>Chưa thể tải dữ liệu dự báo</h1>
        <p>Hệ thống vẫn giữ an toàn cho phiên đăng nhập. Vui lòng thử lại khi dịch vụ dự báo hoạt động.</p>
      </main>
    );
  }

  // A logged-in chief additionally sees the citizen/SMS summary and the SMS send controls.
  // Anonymous viewers get the map only. The Map (client boundary) can't hold a JS Map, so
  // per-area counts cross as a plain object.
  const user = await getSessionUser();
  const chief = user
    ? {
        totalCitizens: countVillagers(user.id),
        smsSent: totalSmsSent(user.id),
        citizensByArea: Object.fromEntries(countVillagersByArea(user.id)),
      }
    : null;

  // Use `||` (not `??`) so an env var that is defined-but-empty — e.g. docker-compose's
  // `${HINATION_TILE_URL:-}` expanding to "" — still falls back to the OSM default.
  return (
    <ForecastMapShell
      forecast={applyOverallLevels(forecast)}
      tileUrl={process.env.HINATION_TILE_URL || "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"}
      chief={chief}
    />
  );
}
