import { db } from "@/lib/db";
import type { VoiceRecording } from "@/types/recording";

type RecordingRow = {
  id: number;
  name: string;
  mime: string;
  duration_ms: number;
  created_at: number;
};

function toRecording(row: RecordingRow): VoiceRecording {
  return {
    id: row.id,
    name: row.name,
    mime: row.mime,
    durationMs: row.duration_ms,
    createdAt: row.created_at,
  };
}

export type RecordingInput = {
  name: string;
  mime: string;
  audio: Buffer;
  durationMs: number;
};

/** Save a captured voice clip for a chief. Returns its metadata (never the bytes). */
export function createRecording(ownerId: number, input: RecordingInput): VoiceRecording {
  const now = Date.now();
  const result = db
    .prepare(
      `INSERT INTO voice_recordings (owner_user_id, name, mime, audio, duration_ms, created_at)
       VALUES (?, ?, ?, ?, ?, ?)`,
    )
    .run(ownerId, input.name, input.mime, input.audio, input.durationMs, now);

  return {
    id: Number(result.lastInsertRowid),
    name: input.name,
    mime: input.mime,
    durationMs: input.durationMs,
    createdAt: now,
  };
}

/** Metadata for every recording a chief owns, newest first. Excludes the audio bytes. */
export function listRecordings(ownerId: number): VoiceRecording[] {
  const rows = db
    .prepare(
      `SELECT id, name, mime, duration_ms, created_at
       FROM voice_recordings
       WHERE owner_user_id = ?
       ORDER BY created_at DESC, id DESC`,
    )
    .all(ownerId) as RecordingRow[];
  return rows.map(toRecording);
}

/** The raw audio bytes + mime for one recording the chief owns, or null if not found. */
export function getRecordingAudio(ownerId: number, id: number): { mime: string; audio: Buffer } | null {
  const row = db
    .prepare("SELECT mime, audio FROM voice_recordings WHERE id = ? AND owner_user_id = ?")
    .get(id, ownerId) as { mime: string; audio: Buffer } | undefined;
  if (!row) return null;
  return { mime: row.mime, audio: row.audio };
}

/** Rename a recording the chief owns. Returns false if no matching row. */
export function renameRecording(ownerId: number, id: number, name: string): boolean {
  const result = db
    .prepare("UPDATE voice_recordings SET name = ? WHERE id = ? AND owner_user_id = ?")
    .run(name, id, ownerId);
  return result.changes > 0;
}

/** Delete a recording the chief owns. Returns false if no matching row. */
export function deleteRecording(ownerId: number, id: number): boolean {
  const result = db
    .prepare("DELETE FROM voice_recordings WHERE id = ? AND owner_user_id = ?")
    .run(id, ownerId);
  return result.changes > 0;
}
