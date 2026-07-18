/**
 * Tiny server-side step logger. Output lands in the terminal running `next dev`
 * (or the server logs in production), so the whole area-brief pipeline can be
 * traced end to end while debugging. Secrets are never logged — only shapes/counts.
 */
export function logStep(scope: string, message: string, data?: Record<string, unknown>) {
  const time = new Date().toISOString();
  const prefix = `[${time}] [${scope}] ${message}`;
  if (data) {
    console.log(prefix, data);
  } else {
    console.log(prefix);
  }
}

export function logError(scope: string, message: string, error: unknown) {
  const time = new Date().toISOString();
  const detail = error instanceof Error ? error.message : String(error);
  console.error(`[${time}] [${scope}] ${message}: ${detail}`);
}
