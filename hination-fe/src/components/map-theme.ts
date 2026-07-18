import type { DangerLevel, DisasterType } from "@/types/forecast";

// Vietnamese weekday abbreviations indexed by Date.getDay() (0 = Sunday).
export const VI_WEEKDAYS = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];

// Combined "overall" levels can reach 0 (reduced API level with no news signal), so
// the map is keyed by number, not the 1–5 DangerLevel, with a grey level-0 swatch.
export const LEVEL_COLORS: Record<number, string> = {
  0: "#94a3b8",
  1: "#22c55e",
  2: "#a3e635",
  3: "#facc15",
  4: "#f97316",
  5: "#ef4444",
};

/** Color for any overall level, clamping out-of-range values to the 0–5 palette. */
export function colorForLevel(level: number): string {
  return LEVEL_COLORS[Math.max(0, Math.min(5, Math.round(level)))] ?? LEVEL_COLORS[0];
}

export const DISASTER_LABELS: Record<DisasterType, string> = {
  flood: "Ngập lụt",
  landslide: "Sạt lở",
  storm: "Mưa bão",
  wildfire: "Cháy rừng",
  wind: "Gió mạnh",
};

// Named danger tiers shown in the "Mức độ nguy hiểm" legend. Each tier groups one
// or more raw danger levels so the 5-level model maps onto the 4 labels in the UI.
export type DangerTier = { key: string; label: string; color: string; levels: number[] };

export const DANGER_TIERS: DangerTier[] = [
  { key: "none", label: "An toàn", color: "#94a3b8", levels: [0] },
  { key: "low", label: "Thấp", color: "#22c55e", levels: [1, 2] },
  { key: "medium", label: "Trung bình", color: "#facc15", levels: [3] },
  { key: "high", label: "Cao", color: "#f97316", levels: [4] },
  { key: "critical", label: "Rất cao", color: "#ef4444", levels: [5] },
];

export function tierForLevel(level: number): DangerTier {
  const clamped = Math.max(0, Math.min(5, Math.round(level)));
  return DANGER_TIERS.find((tier) => tier.levels.includes(clamped)) ?? DANGER_TIERS[1];
}

// A danger level is treated as "dangerous" (red timeline label, unread alert) at 4+.
export const DANGEROUS_LEVEL: DangerLevel = 4;

// Temperature alert thresholds for Điện Biên — mountainous northern Vietnam sees both
// summer heat and winter cold snaps ("rét"), so the alert is the worse of the two.
// Each list is [level2, level3, level4, level5]; heat triggers at/above, cold at/below.
export const HEAT_MAX_C = [35, 37, 39, 41];
export const COLD_MIN_C = [10, 8, 5, 3];

/**
 * Temperature alert level (1–5) derived from a day's min/max °C. Level 1 = comfortable;
 * higher levels flag dangerous heat or cold, whichever is worse. Purely front-end — the
 * temperature already ships in the forecast data, this just scores it.
 */
export function temperatureLevel(weather: { temperatureMaxC: number; temperatureMinC: number }): number {
  let level = 1;
  for (let i = 0; i < HEAT_MAX_C.length; i += 1) {
    if (weather.temperatureMaxC >= HEAT_MAX_C[i]) level = Math.max(level, i + 2);
  }
  for (let i = 0; i < COLD_MIN_C.length; i += 1) {
    if (weather.temperatureMinC <= COLD_MIN_C[i]) level = Math.max(level, i + 2);
  }
  return level;
}

// Forecast-type filter shown in the "Loại thiên tai" panel. A "disaster" filter colours
// the map by the combined danger level and emphasizes areas whose dominant disaster is in
// `matches`; the "temperature" filter instead scores every area by its min/max °C.
export type DisasterFilter = {
  key: string;
  label: string;
  kind: "disaster" | "temperature";
  matches: DisasterType[];
};

export const DISASTER_FILTERS: DisasterFilter[] = [
  { key: "flood", label: "Mưa lũ", kind: "disaster", matches: ["flood", "storm"] },
  { key: "landslide", label: "Sạt lở", kind: "disaster", matches: ["landslide", "wind"] },
  { key: "heat", label: "Nhiệt độ", kind: "temperature", matches: [] },
];
