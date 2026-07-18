import { getAreaBrief } from "@/lib/area-brief";
import { logError, logStep } from "@/lib/log";
import type { ForecastResponse } from "@/types/forecast";

// Guards a single warm run at a time (a 12h interval could otherwise overlap a slow
// startup pass). Module-scoped, so it survives across calls within one server process.
let running = false;

async function fetchForecast(): Promise<ForecastResponse | null> {
  const baseUrl = process.env.HINATION_API_BASE_URL ?? "http://127.0.0.1:8000";
  try {
    const response = await fetch(`${baseUrl}/api/v1/forecasts/latest`, { cache: "no-store" });
    if (!response.ok) {
      logStep("worker", "forecast fetch not ok — skipping", { status: response.status });
      return null;
    }
    return (await response.json()) as ForecastResponse;
  } catch (error) {
    logError("worker", "forecast fetch failed", error);
    return null;
  }
}

/**
 * Pre-generate the news brief (and AI prediction) for every area of the current
 * forecast day. Runs on server startup and every 12 hours. Sequential to stay gentle
 * on the Brave/OpenAI rate limits; each area regenerates only if its cache is stale
 * (getAreaBrief honours the TTL, which is far shorter than the 12h cadence).
 */
export async function warmAllBriefs(trigger: string): Promise<void> {
  if (running) {
    logStep("worker", "skip — a warm run is already in progress", { trigger });
    return;
  }
  running = true;
  const startedAt = Date.now();
  logStep("worker", "warming all area briefs", { trigger });

  try {
    const forecast = await fetchForecast();
    const day = forecast?.days?.[0];
    if (!day) {
      logStep("worker", "no forecast day available — nothing to warm");
      return;
    }

    const date = day.date.slice(0, 10);
    logStep("worker", "generating briefs for day", { date, areas: day.areas.length });

    let ok = 0;
    let failed = 0;
    for (const area of day.areas) {
      try {
        await getAreaBrief(
          {
            areaId: area.id,
            name: area.name,
            adminCode: area.administrativeCode,
            date,
            danger: {
              level: area.danger.level,
              dominantDisaster: area.danger.dominantDisaster,
              message: area.danger.message,
              overallRisk: area.danger.overallRisk,
            },
          },
          false,
        );
        ok += 1;
      } catch (error) {
        failed += 1;
        logError("worker", `area "${area.name}" failed`, error);
      }
    }

    logStep("worker", "warm run complete", { ok, failed, ms: Date.now() - startedAt });
  } catch (error) {
    logError("worker", "warm run failed", error);
  } finally {
    running = false;
  }
}
