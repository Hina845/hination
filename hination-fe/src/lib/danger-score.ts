// Combined danger scoring shared by the server pipeline (area-brief, worker),
// the server-rendered map merge, and any client display. Pure — no imports — so it
// is safe to pull into either bundle.
//
// The forecast API's own level is intentionally reduced by one, and the AI adds a
// 0–2 level judged ONLY from fetched news. The two are summed and capped at 5:
//   overall = min(5, max(0, apiLevel − 1) + predictLevel)
// e.g. API 3 → reduced 2, AI 2 → overall 4.

export const MAX_OVERALL_LEVEL = ;
export const MAX_PREDICT_LEVEL = 2;

/** API danger level (1–5) reduced by one, never below 0. */
export function reduceModelLevel(modelLevel: number): number {
  const level = Number.isFinite(modelLevel) ? Math.round(modelLevel) : 0;
  return Math.max(0, level);
}

/** Clamp the AI's news-based prediction to the allowed 0–2 integer range. */
export function clampPredictLevel(raw: number): number {
  if (!Number.isFinite(raw)) return 0;
  return Math.max(0, Math.min(MAX_PREDICT_LEVEL, Math.round(raw)));
}

/** Combined display level: reduced API level + AI prediction, capped at 5. */
export function overallLevel(modelLevel: number, predictLevel: number): number {
  return Math.min(MAX_OVERALL_LEVEL, reduceModelLevel(modelLevel) + clampPredictLevel(predictLevel));
}
