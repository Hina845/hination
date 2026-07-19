// IP-based geolocation fallback for citizen SOS requests: used only when the browser did
// not (or could not) provide precise GPS coordinates. Degrades to null on any failure,
// mirroring src/lib/forecast.ts, so callers can fall back to the province centroid.

// Province center (also the map's default center in ForecastMap). Last-resort location when
// even IP geolocation is unavailable — keeps the request on the map instead of dropping it.
export const PROVINCE_CENTROID = { lat: 21.65, lng: 103.05 } as const;

// Private / loopback ranges never resolve to a public location, so skip the lookup entirely.
function isPrivateIp(ip: string): boolean {
  if (!ip || ip === "::1" || ip === "127.0.0.1") return true;
  if (ip.startsWith("10.") || ip.startsWith("192.168.")) return true;
  if (ip.startsWith("::ffff:")) return isPrivateIp(ip.slice(7));
  const secondOctet = Number(ip.split(".")[1]);
  if (ip.startsWith("172.") && secondOctet >= 16 && secondOctet <= 31) return true;
  if (ip.startsWith("169.254.") || ip.startsWith("fc") || ip.startsWith("fd")) return true;
  return false;
}

/**
 * Approximate a public IP to {lat, lng} via a free geolocation API. Returns null for
 * private/loopback IPs or on any error (network, non-200, bad payload) so the caller can
 * fall back to PROVINCE_CENTROID. Coarse (city/district level) — only used when GPS is denied.
 */
export async function geolocateIp(ip: string): Promise<{ lat: number; lng: number } | null> {
  if (isPrivateIp(ip)) return null;
  try {
    const response = await fetch(`http://ip-api.com/json/${encodeURIComponent(ip)}?fields=status,lat,lon`, {
      cache: "no-store",
    });
    if (!response.ok) return null;
    const data = (await response.json()) as { status?: string; lat?: number; lon?: number };
    if (data.status !== "success" || typeof data.lat !== "number" || typeof data.lon !== "number") return null;
    return { lat: data.lat, lng: data.lon };
  } catch {
    return null;
  }
}
