"use client";

import dynamic from "next/dynamic";

import type { ForecastResponse } from "@/types/forecast";

const ForecastMap = dynamic(() => import("@/components/ForecastMap"), {
  ssr: false,
  loading: () => <div className="grid min-h-screen place-items-center bg-[#eef2f6] text-base text-slate-500">Đang tải bản đồ…</div>,
});

export default function ForecastMapShell({ forecast, tileUrl }: { forecast: ForecastResponse; tileUrl: string }) {
  return <ForecastMap forecast={forecast} tileUrl={tileUrl} />;
}

