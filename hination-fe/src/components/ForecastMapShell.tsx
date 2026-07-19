"use client";

import dynamic from "next/dynamic";

import type { ForecastResponse } from "@/types/forecast";

// Summary + send context for a logged-in village chief. `null` for anonymous viewers,
// which hides the summary window and every SMS send control on the map.
export type ChiefSummary = {
  totalCitizens: number;
  smsSent: number;
  citizensByArea: Record<string, number>;
};

const ForecastMap = dynamic(() => import("@/components/ForecastMap"), {
  ssr: false,
  loading: () => <div className="grid min-h-screen place-items-center bg-[#eef2f6] text-base text-slate-500">Đang tải bản đồ…</div>,
});

export default function ForecastMapShell({
  forecast,
  tileUrl,
  chief,
}: {
  forecast: ForecastResponse;
  tileUrl: string;
  chief: ChiefSummary | null;
}) {
  return <ForecastMap forecast={forecast} tileUrl={tileUrl} chief={chief} />;
}
