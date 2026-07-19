import type { HelpDot } from "@/components/HelpRequestLayer";

// Demo-only synthetic SOS reports. The real feature stores one row per citizen tap; for a
// visual walkthrough we instead fabricate a dense field of dots from the live forecast so the
// map reads like a province mid-emergency. Nothing here is persisted — it is regenerated in
// memory from the current danger levels each time the inputs change.

export type MockArea = { id: string; lat: number; lng: number; level: number };

// Deterministic PRNG (mulberry32). Using a seeded generator instead of Math.random keeps the
// output pure — the same areas produce the same dot field every render, so points don't jitter
// on unrelated re-renders and React's purity rules stay satisfied.
function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Hard cap (degrees) on how far an area's dots scatter from its centroid, for areas that sit far
// from any neighbour. Each area's actual spread is usually tighter — see the adaptive spread below.
const SPREAD_CAP_DEG = 0.03;
// Fraction of the distance to the nearest neighbouring centroid an area's dots are allowed to
// reach. Below 0.5 two adjacent clusters can never touch, so dots never bleed into another area.
const NEIGHBOUR_FRACTION = 0.4;
// Floor of dots per area so every commune/town shows on the map even at the lowest danger level
// (≥ 45 dots total for the 45 communes — none is ever left empty).
const MIN_PER_AREA = 1;

// Each area's scatter radius, clamped so its dots stay within its own turf: the closer a commune
// sits to its nearest neighbour, the tighter its cluster, so clusters never overlap.
function adaptiveSpreads(areas: MockArea[]): number[] {
  return areas.map((area, index) => {
    let nearest = Infinity;
    areas.forEach((other, otherIndex) => {
      if (otherIndex === index) return;
      const distance = Math.hypot(area.lat - other.lat, area.lng - other.lng);
      if (distance < nearest) nearest = distance;
    });
    if (!Number.isFinite(nearest)) return SPREAD_CAP_DEG;
    return Math.min(SPREAD_CAP_DEG, nearest * NEIGHBOUR_FRACTION);
  });
}

/**
 * Fabricate ~`total` help-request dots spread across `areas`, allocating far more dots to
 * higher-danger areas ("the more dangerous the area, the more dots"). Danger weight is cubed so
 * a level-5 area shows dramatically more distress than a level-1 one, while every area still gets
 * at least `MIN_PER_AREA` so all 45 communes appear. Points use a bounded triangular spread (two
 * summed uniforms, so displacement never exceeds the area's spread) — each area reads as an
 * organic cluster that stays over its own commune and never overlaps a neighbour. Deterministic
 * for a given input, so it can be memoized safely.
 */
export function mockHelpRequests(areas: MockArea[], total = 1_000): HelpDot[] {
  if (areas.length === 0) return [];

  const weights = areas.map((area) => Math.max(area.level, 0) ** 3 + 0.2);
  const weightTotal = weights.reduce((sum, weight) => sum + weight, 0);
  if (weightTotal === 0) return [];

  const spreads = adaptiveSpreads(areas);
  const random = mulberry32(0x50f1a7);
  const dots: HelpDot[] = [];

  areas.forEach((area, index) => {
    const share = Math.max(MIN_PER_AREA, Math.round((weights[index] / weightTotal) * total));
    const spread = spreads[index];
    for (let i = 0; i < share; i += 1) {
      // Two summed uniforms → a rough triangular distribution bounded to ±spread: dots crowd the
      // centroid, thin toward the edge, and never cross into the next commune.
      const jitterLat = (random() + random() - 1) * spread;
      const jitterLng = (random() + random() - 1) * spread;
      // Tag every dot with its area so clustering keeps communes separate — the map never shows
      // fewer dots than there are areas.
      dots.push({ lat: area.lat + jitterLat, lng: area.lng + jitterLng, group: area.id });
    }
  });

  return dots;
}
