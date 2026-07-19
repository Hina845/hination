// Pure geo helpers. NO server-only imports — shared by server code (nearest-commune
// resolution for the rescue SOS list) and client code (nearest-first emergency numbers on
// the citizen EmergencyHelp screen).

import type { Coordinates } from "@/types/forecast";

const EARTH_RADIUS_KM = 6371;

function toRadians(degrees: number): number {
  return (degrees * Math.PI) / 180;
}

/** Great-circle distance between two lat/lng points, in kilometres (Haversine). */
export function haversineKm(a: Coordinates, b: Coordinates): number {
  const dLat = toRadians(b.lat - a.lat);
  const dLng = toRadians(b.lng - a.lng);
  const lat1 = toRadians(a.lat);
  const lat2 = toRadians(b.lat);
  const h =
    Math.sin(dLat / 2) ** 2 + Math.sin(dLng / 2) ** 2 * Math.cos(lat1) * Math.cos(lat2);
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(h));
}

/**
 * The area whose centroid is closest to `point`, or null if `areas` is empty. Used to turn a
 * help request's raw coordinates into a human-readable commune name.
 */
export function nearestArea<T extends { coordinates: Coordinates }>(
  point: Coordinates,
  areas: readonly T[],
): T | null {
  let best: T | null = null;
  let bestKm = Infinity;
  for (const area of areas) {
    const km = haversineKm(point, area.coordinates);
    if (km < bestKm) {
      bestKm = km;
      best = area;
    }
  }
  return best;
}
