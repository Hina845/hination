import { NextResponse } from "next/server";

import { geolocateIp, PROVINCE_CENTROID } from "@/lib/geolocate";
import { createHelpRequest, listRecentHelpRequests } from "@/lib/help-requests";
import { logError, logStep } from "@/lib/log";
import type { HelpRequestSource } from "@/types/help-request";

// better-sqlite3 + the outbound IP-geo fetch require the Node.js runtime, and the dot feed
// must always reflect live submissions, so this must never be statically cached.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const RECENT_WINDOW_MS = 24 * 60 * 60 * 1000; // dots show requests from the last 24h
const REASON_MAX = 300;
const THROTTLE_MS = 10_000; // best-effort per-IP spam guard (1 request / 10s)

// Best-effort in-memory throttle. Resets on redeploy and is per-instance only — not real
// abuse protection, just a cheap brake on accidental double-taps / trivial floods.
const lastSubmitByIp = new Map<string, number>();

function clientIp(request: Request): string {
  const forwarded = request.headers.get("x-forwarded-for");
  if (forwarded) return forwarded.split(",")[0]!.trim();
  return request.headers.get("x-real-ip")?.trim() ?? "";
}

type RequestBody = { lat?: unknown; lng?: unknown; reason?: unknown };

export async function POST(request: Request) {
  logStep("api/help-requests", "POST received");
  const ip = clientIp(request);

  const now = Date.now();
  const last = lastSubmitByIp.get(ip);
  if (ip && last && now - last < THROTTLE_MS) {
    logStep("api/help-requests", "throttled → 429");
    return NextResponse.json({ error: "Vui lòng thử lại sau giây lát" }, { status: 429 });
  }

  let body: RequestBody | null = null;
  try {
    body = (await request.json()) as RequestBody;
  } catch {
    body = null;
  }

  const reasonRaw = typeof body?.reason === "string" ? body.reason.trim() : "";
  const reason = reasonRaw ? reasonRaw.slice(0, REASON_MAX) : null;

  // Precise browser coordinates win. Otherwise fall back to IP geolocation, then the
  // province centroid — a request is never dropped for lack of a fix.
  let lat: number | undefined;
  let lng: number | undefined;
  let source: HelpRequestSource = "gps";
  if (Number.isFinite(body?.lat) && Number.isFinite(body?.lng)) {
    lat = Number(body!.lat);
    lng = Number(body!.lng);
  } else {
    source = "ip";
    const located = ip ? await geolocateIp(ip) : null;
    lat = (located ?? PROVINCE_CENTROID).lat;
    lng = (located ?? PROVINCE_CENTROID).lng;
  }

  try {
    createHelpRequest({ lat, lng, reason, source });
    if (ip) lastSubmitByIp.set(ip, now);
    logStep("api/help-requests", "stored → 200", { source });
    return NextResponse.json({ ok: true });
  } catch (error) {
    logError("api/help-requests", "failed → 500", error);
    return NextResponse.json({ error: "Không thể gửi yêu cầu" }, { status: 500 });
  }
}

export async function GET() {
  const requests = listRecentHelpRequests(Date.now() - RECENT_WINDOW_MS);
  return NextResponse.json({ requests });
}
