// Next.js runs register() once when the server process boots. We use it to warm the
// shared area-brief cache on startup and every 12 hours thereafter, so the map can
// recolor by combined danger level without waiting on a hover to generate anything.
// (Manual per-area refresh still works on demand via /api/areas/brief.)

const TWELVE_HOURS_MS = 12 * 60 * 60 * 1000;

export async function register() {
  // Only the Node.js runtime has SQLite / outbound fetch and should run the worker.
  if (process.env.NEXT_RUNTIME !== "nodejs") return;

  // better-sqlite3 must not be pulled into the Edge bundle, so import lazily here.
  const { warmAllBriefs, warmAllBriefsWhenReady } = await import("@/lib/brief-worker");

  // Kick off the startup warm without blocking server boot. Use the ready-aware variant:
  // on a fresh deploy the backend serves 503 for the first ~2 min while the scheduler
  // builds the forecast, so a one-shot warm would give up and leave the news / AI
  // predict_level overlay empty until the next 12h tick.
  void warmAllBriefsWhenReady("startup");

  // Schedule the recurring 12h warm exactly once per process (dev hot-reload safe).
  const globalForWorker = globalThis as typeof globalThis & { __briefWarmTimer?: ReturnType<typeof setInterval> };
  if (!globalForWorker.__briefWarmTimer) {
    globalForWorker.__briefWarmTimer = setInterval(() => void warmAllBriefs("interval-12h"), TWELVE_HOURS_MS);
    // Don't keep the process alive just for this timer.
    globalForWorker.__briefWarmTimer.unref?.();
  }
}
