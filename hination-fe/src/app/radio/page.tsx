import { redirect } from "next/navigation";

import ManageSidebar from "@/components/ManageSidebar";
import RadioStudio, { type RadioAlert } from "@/components/RadioStudio";
import { getSessionUser } from "@/lib/auth";
import { listBroadcasts } from "@/lib/broadcasts";
import { areaOptionsFrom, getForecast } from "@/lib/forecast";
import { DISASTER_LABELS, tierForLevel } from "@/components/map-theme";
import { listRecordings } from "@/lib/recordings";
import { countVillagersByArea } from "@/lib/villagers";
import type { ForecastArea, ForecastResponse } from "@/types/forecast";

// better-sqlite3 needs the Node runtime, and the studio's data (recordings, drafts,
// villager counts) is per-session, so this screen must never be statically cached.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Same display rule the map uses: combined "overall" level, falling back to raw API level.
function displayLevel(area: ForecastArea): number {
  return area.danger.overallLevel ?? area.danger.level;
}

// Contiguous peak-hour window for an area, e.g. "20:00–23:00". Reads the hours whose level
// matches the day peak and spans min→max. Falls back to the danger.peakTime string.
function peakWindow(area: ForecastArea): string {
  const peak = Math.max(...area.hours.map((hour) => hour.overallLevel ?? hour.level));
  const atPeak = area.hours.filter((hour) => (hour.overallLevel ?? hour.level) >= peak);
  if (atPeak.length === 0) return area.danger.peakTime;
  const start = Math.min(...atPeak.map((hour) => hour.hourOfDay));
  const end = Math.max(...atPeak.map((hour) => hour.hourOfDay));
  const pad = (hour: number) => `${String(hour).padStart(2, "0")}:00`;
  return `${pad(start)}–${pad(Math.min(23, end + 1))}`;
}

// Build the "current alert" summary from the forecast's first (today) day: the most
// dangerous areas, their dominant disaster, rainfall and peak window. Drives the red alert
// card and the AI risk-summary bullets in the studio. Returns null if there is no forecast.
function deriveAlert(forecast: ForecastResponse | null): RadioAlert | null {
  const day = forecast?.days[0];
  if (!day || day.areas.length === 0) return null;

  const ranked = [...day.areas].sort((a, b) => displayLevel(b) - displayLevel(a));
  const primary = ranked[0];
  const level = displayLevel(primary);
  const tier = tierForLevel(level);

  // The areas sharing the alert: everything within one level of the worst, capped so the
  // header stays readable.
  const band = ranked.filter((area) => displayLevel(area) >= Math.max(1, level - 1)).slice(0, 4);

  return {
    disasterLabel: DISASTER_LABELS[primary.danger.dominantDisaster],
    communeName: primary.name,
    areaNames: band.map((area) => area.name),
    level,
    tierLabel: tier.label,
    tierColor: tier.color,
    rainfallMm: Math.round(primary.weather.rainfallTotalMm),
    windGustKmh: Math.round(primary.weather.windGustMaxKmh),
    peakWindow: peakWindow(primary),
    dominantDisaster: primary.danger.dominantDisaster,
    riskMessage: primary.danger.message,
    riskAreaIds: band.map((area) => area.id),
  };
}

export default async function RadioPage() {
  const user = await getSessionUser();
  if (!user) {
    redirect("/login");
  }

  const forecast = await getForecast();
  const citizensByArea = Object.fromEntries(countVillagersByArea(user.id));
  const areaOptions = areaOptionsFrom(forecast, citizensByArea);
  const alert = deriveAlert(forecast);
  const recordings = listRecordings(user.id);
  const broadcasts = listBroadcasts(user.id);

  return (
    <div className="flex min-h-svh bg-[#eef2f6] text-[#0f172a]">
      <ManageSidebar active="radio" />
      <RadioStudio
        alert={alert}
        areaOptions={areaOptions}
        recordings={recordings}
        broadcasts={broadcasts}
      />
    </div>
  );
}
