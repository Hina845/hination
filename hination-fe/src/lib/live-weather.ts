// Live weather from Open-Meteo (https://open-meteo.com) — free, no API key, CORS-enabled,
// so the browser can call it directly. The backend forecast ships pre-computed daily
// aggregates that can lag real conditions; this fetches the accurate *current* reading
// plus the selected day's aggregate straight from Open-Meteo for the hovered area, so the
// hover card shows the right numbers for the exact time instead of a stale snapshot.

export type LiveCurrent = {
  time: string; // ISO local time (Asia/Bangkok, UTC+7)
  temperatureC: number;
  humidityPct: number;
  precipitationMm: number;
  windGustKmh: number;
  conditionCode: number;
};

export type LiveDaily = {
  temperatureMinC: number;
  temperatureMaxC: number;
  rainfallTotalMm: number;
  windGustMaxKmh: number;
};

export type LiveWeather = {
  current: LiveCurrent | null;
  daily: LiveDaily | null;
};

const OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast";

const round = (value: unknown): number =>
  typeof value === "number" && Number.isFinite(value) ? Math.round(value) : 0;

// WMO weather code → short Vietnamese condition label (open-meteo current.weather_code).
export function weatherCodeLabel(code: number): string {
  if (code === 0) return "Trời quang";
  if (code <= 2) return "Ít mây";
  if (code === 3) return "Nhiều mây";
  if (code <= 48) return "Sương mù";
  if (code <= 57) return "Mưa phùn";
  if (code <= 67) return "Mưa";
  if (code <= 77) return "Tuyết";
  if (code <= 82) return "Mưa rào";
  if (code <= 86) return "Mưa tuyết";
  return "Dông";
}

/**
 * Fetch current conditions + one day's aggregate for a point from Open-Meteo.
 * `date` is a YYYY-MM-DD string in the province's local time (UTC+7). Throws on a
 * network/HTTP error so the caller can fall back to the pre-computed forecast values.
 */
export async function fetchLiveWeather(
  lat: number,
  lng: number,
  date: string,
  signal?: AbortSignal,
): Promise<LiveWeather> {
  const params = new URLSearchParams({
    latitude: lat.toFixed(4),
    longitude: lng.toFixed(4),
    current: "temperature_2m,relative_humidity_2m,precipitation,wind_gusts_10m,weather_code",
    daily: "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_gusts_10m_max",
    timezone: "Asia/Bangkok",
    start_date: date,
    end_date: date,
  });

  const response = await fetch(`${OPEN_METEO_URL}?${params.toString()}`, { signal });
  if (!response.ok) throw new Error(`Open-Meteo ${response.status}`);
  const data = (await response.json()) as {
    current?: Record<string, unknown>;
    daily?: Record<string, unknown[]>;
  };

  const c = data.current;
  const current: LiveCurrent | null = c
    ? {
        time: String(c.time ?? ""),
        temperatureC: round(c.temperature_2m),
        humidityPct: round(c.relative_humidity_2m),
        precipitationMm: Math.round((Number(c.precipitation) || 0) * 10) / 10,
        windGustKmh: round(c.wind_gusts_10m),
        conditionCode: round(c.weather_code),
      }
    : null;

  const d = data.daily;
  const daily: LiveDaily | null =
    d && Array.isArray(d.time) && d.time.length > 0
      ? {
          temperatureMinC: round(d.temperature_2m_min?.[0]),
          temperatureMaxC: round(d.temperature_2m_max?.[0]),
          rainfallTotalMm: Math.round((Number(d.precipitation_sum?.[0]) || 0) * 10) / 10,
          windGustMaxKmh: round(d.wind_gusts_10m_max?.[0]),
        }
      : null;

  return { current, daily };
}
