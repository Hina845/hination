import { db } from "@/lib/db";
import type { HelpRequest, HelpRequestSource } from "@/types/help-request";

type HelpRequestRow = {
  id: number;
  lat: number;
  lng: number;
  reason: string | null;
  place: string | null;
  source: string;
  created_at: number;
};

function toHelpRequest(row: HelpRequestRow): HelpRequest {
  return {
    id: row.id,
    lat: row.lat,
    lng: row.lng,
    reason: row.reason,
    place: row.place,
    source: row.source === "gps" ? "gps" : "ip",
    createdAt: row.created_at,
  };
}

/** Record one citizen SOS. Global / anonymous — no owner. Returns the new row id. */
export function createHelpRequest(input: {
  lat: number;
  lng: number;
  reason: string | null;
  place: string | null;
  source: HelpRequestSource;
}): number {
  const result = db
    .prepare(
      `INSERT INTO help_requests (lat, lng, reason, place, source, created_at)
       VALUES (?, ?, ?, ?, ?, ?)`,
    )
    .run(input.lat, input.lng, input.reason, input.place, input.source, Date.now());
  return Number(result.lastInsertRowid);
}

/**
 * Help requests created at or after `sinceMs`, newest first. Drives the live map dots and the
 * rescue console. Defaults to the last 24h so callers that just want "recent" needn't compute
 * the window (and don't call Date.now() inside a React render).
 */
export function listRecentHelpRequests(sinceMs: number = Date.now() - 24 * 60 * 60 * 1000): HelpRequest[] {
  const rows = db
    .prepare(
      `SELECT id, lat, lng, reason, place, source, created_at
       FROM help_requests
       WHERE created_at >= ?
       ORDER BY created_at DESC, id DESC`,
    )
    .all(sinceMs) as HelpRequestRow[];
  return rows.map(toHelpRequest);
}
