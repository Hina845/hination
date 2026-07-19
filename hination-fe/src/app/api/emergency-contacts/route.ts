import { NextResponse } from "next/server";

import { listActiveEmergencyContacts } from "@/lib/emergency-contacts";

// better-sqlite3 requires the Node.js runtime, and the number list changes as chiefs/visitors
// add entries (and anonymous ones expire), so this must never be statically cached.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Public read consumed by the citizen SOS screen (EmergencyHelp on /app), which sorts the
// numbers nearest-first client-side using the caller's location.
export function GET() {
  const contacts = listActiveEmergencyContacts(Date.now());
  return NextResponse.json({ contacts });
}
