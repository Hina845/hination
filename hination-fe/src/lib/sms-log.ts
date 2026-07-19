import { db } from "@/lib/db";
import type { SmsLog } from "@/types/sms";

type SmsLogRow = {
  id: number;
  area_ids: string;
  message: string;
  recipient_count: number;
  created_at: number;
};

function toSmsLog(row: SmsLogRow): SmsLog {
  let areaIds: string[] = [];
  try {
    const parsed = JSON.parse(row.area_ids);
    if (Array.isArray(parsed)) areaIds = parsed.filter((value): value is string => typeof value === "string");
  } catch {
    areaIds = [];
  }
  return {
    id: row.id,
    areaIds,
    message: row.message,
    recipientCount: row.recipient_count,
    createdAt: row.created_at,
  };
}

/** Record one emergency SMS blast for the chief. `areaIds` empty = sent to every villager. */
export function logSms(
  ownerId: number,
  input: { areaIds: string[]; message: string; recipientCount: number },
): void {
  db.prepare(
    `INSERT INTO sms_logs (owner_user_id, area_ids, message, recipient_count, created_at)
     VALUES (?, ?, ?, ?, ?)`,
  ).run(ownerId, JSON.stringify(input.areaIds), input.message, input.recipientCount, Date.now());
}

/** All SMS blasts the chief has sent, newest first. */
export function listSmsLogs(ownerId: number): SmsLog[] {
  const rows = db
    .prepare(
      `SELECT id, area_ids, message, recipient_count, created_at
       FROM sms_logs
       WHERE owner_user_id = ?
       ORDER BY created_at DESC, id DESC`,
    )
    .all(ownerId) as SmsLogRow[];
  return rows.map(toSmsLog);
}

/** Total recipients messaged across all of the chief's blasts (the summary "SMS sent" count). */
export function totalSmsSent(ownerId: number): number {
  const row = db
    .prepare("SELECT COALESCE(SUM(recipient_count), 0) AS total FROM sms_logs WHERE owner_user_id = ?")
    .get(ownerId) as { total: number };
  return row.total;
}
