import { db } from "@/lib/db";
import type { Villager } from "@/types/villager";

type VillagerRow = {
  id: number;
  name: string;
  phone: string;
  address: string | null;
  area_id: string | null;
  created_at: number;
};

function toVillager(row: VillagerRow): Villager {
  return {
    id: row.id,
    name: row.name,
    phone: row.phone,
    address: row.address,
    areaId: row.area_id,
    createdAt: row.created_at,
  };
}

export type VillagerInput = {
  name: string;
  phone: string;
  address: string;
  areaId: string | null;
};

/**
 * All villagers owned by a chief, newest first. An optional keyword filters on
 * name/phone/address (case-insensitive). Always scoped by owner_user_id so a chief
 * only ever sees their own list.
 */
export function listVillagers(ownerId: number, search?: string): Villager[] {
  const keyword = search?.trim();
  if (keyword) {
    const like = `%${keyword.toLowerCase()}%`;
    const rows = db
      .prepare(
        `SELECT id, name, phone, address, area_id, created_at
         FROM villagers
         WHERE owner_user_id = ?
           AND (lower(name) LIKE ? OR lower(phone) LIKE ? OR lower(coalesce(address, '')) LIKE ?)
         ORDER BY created_at DESC, id DESC`,
      )
      .all(ownerId, like, like, like) as VillagerRow[];
    return rows.map(toVillager);
  }

  const rows = db
    .prepare(
      `SELECT id, name, phone, address, area_id, created_at
       FROM villagers
       WHERE owner_user_id = ?
       ORDER BY created_at DESC, id DESC`,
    )
    .all(ownerId) as VillagerRow[];
  return rows.map(toVillager);
}

/**
 * Total villager count for a chief. Uses COUNT(*) so callers that only need the number
 * (e.g. the map summary) don't materialize every row — matters once the list is large.
 */
export function countVillagers(ownerId: number): number {
  const row = db
    .prepare("SELECT COUNT(*) AS count FROM villagers WHERE owner_user_id = ?")
    .get(ownerId) as { count: number };
  return row.count;
}

/**
 * Count of villagers per forecast area for a chief, keyed by `area_id`. Villagers with no
 * area assigned are omitted. Used for the map's per-area citizen counts and the manage
 * SMS scope selector.
 */
export function countVillagersByArea(ownerId: number): Map<string, number> {
  const rows = db
    .prepare(
      `SELECT area_id, COUNT(*) AS count
       FROM villagers
       WHERE owner_user_id = ? AND area_id IS NOT NULL
       GROUP BY area_id`,
    )
    .all(ownerId) as { area_id: string; count: number }[];
  return new Map(rows.map((row) => [row.area_id, row.count]));
}

export function createVillager(ownerId: number, input: VillagerInput): Villager {
  const now = Date.now();
  const address = input.address.trim() || null;
  const areaId = input.areaId?.trim() || null;
  const result = db
    .prepare(
      `INSERT INTO villagers (owner_user_id, name, phone, address, area_id, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
    )
    .run(ownerId, input.name.trim(), input.phone.trim(), address, areaId, now, now);

  return {
    id: Number(result.lastInsertRowid),
    name: input.name.trim(),
    phone: input.phone.trim(),
    address,
    areaId,
    createdAt: now,
  };
}

/** Update a villager the chief owns. Returns false if no matching row (wrong owner or id). */
export function updateVillager(ownerId: number, id: number, input: VillagerInput): boolean {
  const address = input.address.trim() || null;
  const areaId = input.areaId?.trim() || null;
  const result = db
    .prepare(
      `UPDATE villagers
       SET name = ?, phone = ?, address = ?, area_id = ?, updated_at = ?
       WHERE id = ? AND owner_user_id = ?`,
    )
    .run(input.name.trim(), input.phone.trim(), address, areaId, Date.now(), id, ownerId);
  return result.changes > 0;
}

/** Delete a villager the chief owns. Returns false if no matching row. */
export function deleteVillager(ownerId: number, id: number): boolean {
  const result = db
    .prepare("DELETE FROM villagers WHERE id = ? AND owner_user_id = ?")
    .run(id, ownerId);
  return result.changes > 0;
}
