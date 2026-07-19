import { db } from "@/lib/db";
import type { EmergencyContact } from "@/types/emergency-contact";

const ANONYMOUS_TTL_MS = 48 * 60 * 60 * 1000; // non-registered numbers live 48h

type EmergencyContactRow = {
  id: number;
  name: string;
  phone: string;
  area_id: string | null;
  area_name: string | null;
  lat: number | null;
  lng: number | null;
  owner_user_id: number | null;
  created_at: number;
  expires_at: number | null;
};

function toEmergencyContact(row: EmergencyContactRow): EmergencyContact {
  return {
    id: row.id,
    name: row.name,
    phone: row.phone,
    areaId: row.area_id,
    areaName: row.area_name,
    lat: row.lat,
    lng: row.lng,
    createdAt: row.created_at,
    expiresAt: row.expires_at,
  };
}

export type EmergencyContactInput = {
  name: string;
  phone: string;
  areaId: string | null;
  areaName: string | null;
  lat: number | null;
  lng: number | null;
};

/**
 * Record an emergency number. `ownerId` is the logged-in chief, or null when a non-registered
 * visitor adds it — anonymous numbers expire 48h after creation, chief numbers never expire.
 * Returns the new row id.
 */
export function createEmergencyContact(input: EmergencyContactInput, ownerId: number | null): number {
  const now = Date.now();
  const expiresAt = ownerId ? null : now + ANONYMOUS_TTL_MS;
  const result = db
    .prepare(
      `INSERT INTO emergency_contacts
         (owner_user_id, name, phone, area_id, area_name, lat, lng, created_at, expires_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .run(
      ownerId,
      input.name.trim(),
      input.phone.trim(),
      input.areaId,
      input.areaName,
      input.lat,
      input.lng,
      now,
      expiresAt,
    );
  return Number(result.lastInsertRowid);
}

/**
 * Every currently-active emergency number, newest first. Global (across owners, including
 * anonymous rows) so the citizen SOS screen sees them all; expired anonymous rows are filtered
 * out by `nowMs`.
 */
export function listActiveEmergencyContacts(nowMs: number = Date.now()): EmergencyContact[] {
  const rows = db
    .prepare(
      `SELECT id, name, phone, area_id, area_name, lat, lng, owner_user_id, created_at, expires_at
       FROM emergency_contacts
       WHERE expires_at IS NULL OR expires_at >= ?
       ORDER BY created_at DESC, id DESC`,
    )
    .all(nowMs) as EmergencyContactRow[];
  return rows.map(toEmergencyContact);
}

/** Delete a number the chief owns. Returns false if no matching row (wrong owner or anonymous). */
export function deleteEmergencyContact(ownerId: number, id: number): boolean {
  const result = db
    .prepare("DELETE FROM emergency_contacts WHERE id = ? AND owner_user_id = ?")
    .run(id, ownerId);
  return result.changes > 0;
}
