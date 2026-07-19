import { db } from "@/lib/db";
import type { Broadcast, BroadcastChannel, BroadcastStatus, BroadcastVoice } from "@/types/broadcast";

type BroadcastRow = {
  id: number;
  status: string;
  area_ids: string;
  message: string;
  channels: string;
  voice: string;
  repeat_count: number;
  repeat_gap_minutes: number;
  scheduled_at: number | null;
  recipient_count: number;
  created_at: number;
};

const CHANNELS: BroadcastChannel[] = ["loudspeaker", "sms", "zalo"];

function parseStringArray(raw: string): string[] {
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed.filter((value): value is string => typeof value === "string");
  } catch {
    /* fall through */
  }
  return [];
}

function parseChannels(raw: string): BroadcastChannel[] {
  const values = parseStringArray(raw);
  return CHANNELS.filter((channel) => values.includes(channel));
}

function parseVoice(raw: string): BroadcastVoice {
  try {
    const parsed = JSON.parse(raw) as BroadcastVoice;
    if (parsed?.kind === "recording" && typeof parsed.recordingId === "number") return parsed;
    if (parsed?.kind === "tts" && (parsed.id === "kinh" || parsed.id === "hmong")) return parsed;
  } catch {
    /* fall through */
  }
  return { kind: "tts", id: "kinh" };
}

function toBroadcast(row: BroadcastRow): Broadcast {
  return {
    id: row.id,
    status: row.status as BroadcastStatus,
    areaIds: parseStringArray(row.area_ids),
    message: row.message,
    channels: parseChannels(row.channels),
    voice: parseVoice(row.voice),
    repeat: row.repeat_count,
    repeatGapMinutes: row.repeat_gap_minutes,
    scheduledAt: row.scheduled_at,
    recipientCount: row.recipient_count,
    createdAt: row.created_at,
  };
}

export type BroadcastInput = {
  status: BroadcastStatus;
  areaIds: string[];
  message: string;
  channels: BroadcastChannel[];
  voice: BroadcastVoice;
  repeat: number;
  repeatGapMinutes: number;
  scheduledAt: number | null;
  recipientCount: number;
};

/** Record one composed broadcast (draft or sent) for the chief. */
export function createBroadcast(ownerId: number, input: BroadcastInput): Broadcast {
  const now = Date.now();
  const result = db
    .prepare(
      `INSERT INTO broadcasts
         (owner_user_id, status, area_ids, message, channels, voice,
          repeat_count, repeat_gap_minutes, scheduled_at, recipient_count, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .run(
      ownerId,
      input.status,
      JSON.stringify(input.areaIds),
      input.message,
      JSON.stringify(input.channels),
      JSON.stringify(input.voice),
      input.repeat,
      input.repeatGapMinutes,
      input.scheduledAt,
      input.recipientCount,
      now,
    );

  return { id: Number(result.lastInsertRowid), createdAt: now, ...input };
}

/** Every broadcast the chief has composed (drafts + sent), newest first. */
export function listBroadcasts(ownerId: number, limit = 20): Broadcast[] {
  const rows = db
    .prepare(
      `SELECT id, status, area_ids, message, channels, voice, repeat_count,
              repeat_gap_minutes, scheduled_at, recipient_count, created_at
       FROM broadcasts
       WHERE owner_user_id = ?
       ORDER BY created_at DESC, id DESC
       LIMIT ?`,
    )
    .all(ownerId, limit) as BroadcastRow[];
  return rows.map(toBroadcast);
}

/** Delete a broadcast/draft the chief owns. Returns false if no matching row. */
export function deleteBroadcast(ownerId: number, id: number): boolean {
  const result = db
    .prepare("DELETE FROM broadcasts WHERE id = ? AND owner_user_id = ?")
    .run(id, ownerId);
  return result.changes > 0;
}
