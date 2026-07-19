import type { AreaOption } from "@/types/area";
import type { ForecastResponse } from "@/types/forecast";

/**
 * Fetch the latest combined forecast snapshot from the Python backend. Shared by the map
 * page (`/app`) and the manage page (`/manage`, which needs the area list + danger levels
 * for the SMS scope selector). Returns null on any failure so callers can degrade
 * gracefully instead of throwing.
 */
export async function getForecast(): Promise<ForecastResponse | null> {
  const baseUrl = process.env.HINATION_API_BASE_URL ?? "http://127.0.0.1:8000";
  try {
    const response = await fetch(`${baseUrl}/api/v1/forecasts/latest`, { cache: "no-store" });
    if (!response.ok) return null;
    return (await response.json()) as ForecastResponse;
  } catch {
    return null;
  }
}

/**
 * Build the per-area option list from a forecast's first (current) day, folding in each
 * area's tagged-villager count. `level` uses the server-injected overall level, falling
 * back to the raw API level — the same rule the map uses (see ForecastMap.displayLevel).
 * Sorted by danger level (highest first) then name so the most urgent areas surface.
 */
export function areaOptionsFrom(
  forecast: ForecastResponse | null,
  citizensByArea: Record<string, number>,
): AreaOption[] {
  const areas = forecast?.days[0]?.areas ?? [];
  return areas
    .map((area) => ({
      id: area.id,
      name: area.name,
      level: area.danger.overallLevel ?? area.danger.level,
      count: citizensByArea[area.id] ?? 0,
    }))
    .sort((a, b) => b.level - a.level || a.name.localeCompare(b.name, "vi"));
}

