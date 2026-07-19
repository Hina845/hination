export type DangerLevel = 1 | 2 | 3 | 4 | 5;
export type DisasterType = "flood" | "landslide" | "storm" | "wildfire" | "wind";

export type Coordinates = { lat: number; lng: number };
export type DailyWeather = {
  temperatureMinC: number;
  temperatureMaxC: number;
  rainfallTotalMm: number;
  windGustMaxKmh: number;
  humidityAveragePct: number;
  cloudCoverAveragePct: number;
};
export type DailyDanger = {
  peakTime: string;
  overallRisk: number;
  level: DangerLevel; // raw API level (1–5); still what the AI brief request is keyed on
  dominantDisaster: DisasterType;
  risks: Record<"flood" | "landslide" | "storm" | "wildfire", number>;
  message: string;
  // Injected server-side (see app/app/page.tsx). `overallLevel` = (level − 1) + AI
  // news prediction (0–2), capped at 5, and drives all map coloring/labels.
  overallLevel?: number;
  predictLevel?: number; // AI news-based prediction, 0–2 (0 when not yet warmed)
};
// One hour of the danger dimension for an area. The model is hourly under the hood
// (168 points/area); this is a single point so the timeline can scrub to a specific
// hour. Weather stays a daily summary on the area — only danger is hour-accurate.
export type ForecastHour = {
  time: string; // ISO datetime for this hour
  hourOfDay: number; // 0–23 position within the selected day (drives the scrubber index)
  level: DangerLevel; // raw API level (1–5)
  overallRisk: number;
  dominantDisaster: DisasterType;
  risks: Record<"flood" | "landslide" | "storm" | "wildfire", number>;
  message: string;
  // Injected server-side (see app/app/page.tsx), mirroring DailyDanger.overallLevel so
  // the map colors an individual hour with the same reduced-API + news blend as the day.
  overallLevel?: number;
  predictLevel?: number;
};
export type ForecastArea = {
  id: string;
  administrativeCode: string;
  name: string;
  coordinates: Coordinates;
  weather: DailyWeather;
  danger: DailyDanger;
  hours: ForecastHour[]; // 24 entries for this area on this day
};
export type ForecastDay = {
  dayOffset: number;
  date: string;
  maximumAlertLevel: DangerLevel;
  areas: ForecastArea[];
};
export type ForecastResponse = {
  forecastRunId: string;
  weatherGeneratedAt: string;
  riskGeneratedAt: string;
  timezone: string;
  stale: boolean;
  forecastHorizonDays: 7;
  days: ForecastDay[];
};

