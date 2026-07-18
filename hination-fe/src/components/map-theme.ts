import type { DangerLevel, DisasterType } from "@/types/forecast";

export const LEVEL_COLORS: Record<DangerLevel, string> = {
  1: "#22c55e",
  2: "#a3e635",
  3: "#facc15",
  4: "#f97316",
  5: "#ef4444",
};

export const DISASTER_LABELS: Record<DisasterType, string> = {
  flood: "Ngập lụt",
  landslide: "Sạt lở",
  storm: "Mưa bão",
  wildfire: "Cháy rừng",
  wind: "Gió mạnh",
};

