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

// Disaster-type filter shown in the "Loại thiên tai" panel. `matches` maps each UI
// option onto the disaster types present in the forecast data.
export type DisasterFilter = { key: string; label: string; matches: DisasterType[] };

export const DISASTER_FILTERS: DisasterFilter[] = [
  { key: "flood", label: "Mưa lũ", matches: ["flood", "storm"] },
  { key: "heat", label: "Nhiệt độ", matches: ["wildfire"] },
  { key: "quake", label: "Động đất", matches: [] },
  { key: "landslide", label: "Sạt lở", matches: ["landslide", "wind"] },
];
