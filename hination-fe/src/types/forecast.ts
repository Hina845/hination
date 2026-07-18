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
  level: DangerLevel;
  dominantDisaster: DisasterType;
  risks: Record<"flood" | "landslide" | "storm" | "wildfire", number>;
  message: string;
};
export type ForecastArea = {
  id: string;
  administrativeCode: string;
  name: string;
  coordinates: Coordinates;
  weather: DailyWeather;
  danger: DailyDanger;
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

