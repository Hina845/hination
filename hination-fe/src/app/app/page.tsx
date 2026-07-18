import { redirect } from "next/navigation";

import ForecastMapShell from "@/components/ForecastMapShell";
import { getSessionUser } from "@/lib/auth";
import type { ForecastResponse } from "@/types/forecast";

async function getForecast(): Promise<ForecastResponse | null> {
  const baseUrl = process.env.HINATION_API_BASE_URL ?? "http://127.0.0.1:8000";
  try {
    const response = await fetch(`${baseUrl}/api/v1/forecasts/latest`, { cache: "no-store" });
    if (!response.ok) return null;
    return (await response.json()) as ForecastResponse;
  } catch {
    return null;
  }
}

export default async function AppPage() {
  const user = await getSessionUser();

  if (!user) {
    redirect("/login");
  }

  const forecast = await getForecast();
  if (!forecast) {
    return (
      <main className="forecast-unavailable">
        <span>DB–MWAI</span>
        <h1>Chưa thể tải dữ liệu dự báo</h1>
        <p>Hệ thống vẫn giữ an toàn cho phiên đăng nhập. Vui lòng thử lại khi dịch vụ dự báo hoạt động.</p>
      </main>
    );
  }

  return <ForecastMapShell forecast={forecast} tileUrl={process.env.HINATION_TILE_URL ?? "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"} />;
}
