import { mkdirSync } from "node:fs";
import { join } from "node:path";

import bcrypt from "bcryptjs";
import Database from "better-sqlite3";

const databaseDirectory = join(process.cwd(), "data");
const databasePath = join(databaseDirectory, "hination.sqlite");

mkdirSync(databaseDirectory, { recursive: true });

const globalForDatabase = globalThis as typeof globalThis & {
  hinationDatabase?: Database.Database;
};

export const db = globalForDatabase.hinationDatabase ?? new Database(databasePath);

if (process.env.NODE_ENV !== "production") {
  globalForDatabase.hinationDatabase = db;
}

db.pragma("journal_mode = WAL");
// Default busy timeout is 0, so a writer that finds the file locked throws SQLITE_BUSY
// immediately. During `next build` the 8 parallel page-data workers each open this file
// and write (migration + admin seed) at import time; without a timeout they collide.
// Wait up to 5s for the lock instead of failing.
db.pragma("busy_timeout = 5000");
db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at INTEGER NOT NULL
  );

  CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at INTEGER NOT NULL,
    created_at INTEGER NOT NULL
  );

  CREATE INDEX IF NOT EXISTS sessions_token_hash_idx ON sessions(token_hash);

  -- Shared (account-agnostic) cache of AI-generated area news briefs.
  -- One row per area per forecast day; refreshed on a TTL or manual refetch.
  CREATE TABLE IF NOT EXISTS area_briefs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    area_id TEXT NOT NULL,
    brief_date TEXT NOT NULL,
    headline TEXT NOT NULL,
    summary TEXT NOT NULL,
    sources TEXT NOT NULL,
    model TEXT,
    generated_at INTEGER NOT NULL,
    UNIQUE(area_id, brief_date)
  );

  -- Villagers managed by a village chief for fast emergency SMS. Scoped per chief:
  -- owner_user_id is the logged-in user (chief) who owns the record.
  CREATE TABLE IF NOT EXISTS villagers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    address TEXT,
    area_id TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
  );

  CREATE INDEX IF NOT EXISTS villagers_owner_idx ON villagers(owner_user_id);

  -- History of emergency SMS blasts, scoped per chief. 'area_ids' is a JSON array of the
  -- forecast area ids targeted (empty array = every villager the chief owns). SMS itself is
  -- still a stub (see src/lib/sms.ts); this table makes the sent count and history real.
  CREATE TABLE IF NOT EXISTS sms_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    area_ids TEXT NOT NULL,
    message TEXT NOT NULL,
    recipient_count INTEGER NOT NULL,
    created_at INTEGER NOT NULL
  );

  CREATE INDEX IF NOT EXISTS sms_logs_owner_idx ON sms_logs(owner_user_id);

  CREATE INDEX IF NOT EXISTS area_briefs_date_idx ON area_briefs(brief_date);

  -- Citizen SOS requests. Global / anonymous (no owner_user_id): residents have no account,
  -- so any device can submit one and every map viewer sees the aggregated dots. 'source' is
  -- 'gps' when the browser gave precise coordinates, 'ip' when we fell back to IP geolocation
  -- (or the province centroid). Aged off the map by a 24h window on read; not deleted here.
  CREATE TABLE IF NOT EXISTS help_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    reason TEXT,
    source TEXT NOT NULL,
    created_at INTEGER NOT NULL
  );

  CREATE INDEX IF NOT EXISTS help_requests_created_idx ON help_requests(created_at);

  -- Emergency phone numbers shown to citizens on the SOS screen. Added on /rescue (open to
  -- everyone). owner_user_id is the chief who added it, or NULL when a non-registered visitor
  -- added it. expires_at is NULL for chief-added numbers (permanent) and a timestamp for
  -- anonymous ones (48h after creation) — aged off on read. area_id/area_name/lat/lng capture
  -- the served commune + centroid so the citizen screen can sort numbers nearest-first.
  CREATE TABLE IF NOT EXISTS emergency_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    area_id TEXT,
    area_name TEXT,
    lat REAL,
    lng REAL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER
  );

  CREATE INDEX IF NOT EXISTS emergency_contacts_expires_idx ON emergency_contacts(expires_at);

  -- Voice recordings the chief captures in the radio studio (their own voice) to reuse
  -- as the spoken alert instead of an AI TTS voice. Scoped per chief. 'audio' is the raw
  -- encoded clip (webm/mp4 from MediaRecorder); it is streamed back on demand from
  -- /api/recordings/[id] rather than ever crossing into a React payload.
  CREATE TABLE IF NOT EXISTS voice_recordings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    mime TEXT NOT NULL,
    audio BLOB NOT NULL,
    duration_ms INTEGER NOT NULL,
    created_at INTEGER NOT NULL
  );

  CREATE INDEX IF NOT EXISTS voice_recordings_owner_idx ON voice_recordings(owner_user_id);

  -- Alerts composed in the radio studio. A 'draft' is saved for later; a 'sent'/'scheduled'
  -- row is an actual broadcast (the multi-channel counterpart of sms_logs). 'area_ids',
  -- 'channels' and 'voice' are JSON. Broadcasting itself reuses the SMS stub for the SMS
  -- channel; loudspeaker/Zalo are simulated (see src/lib/broadcasts.ts).
  CREATE TABLE IF NOT EXISTS broadcasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    area_ids TEXT NOT NULL,
    message TEXT NOT NULL,
    channels TEXT NOT NULL,
    voice TEXT NOT NULL,
    repeat_count INTEGER NOT NULL,
    repeat_gap_minutes INTEGER NOT NULL,
    scheduled_at INTEGER,
    recipient_count INTEGER NOT NULL,
    created_at INTEGER NOT NULL
  );

  CREATE INDEX IF NOT EXISTS broadcasts_owner_idx ON broadcasts(owner_user_id);
`);

// Migration: `predict_level` (AI news-based danger prediction, 0–2) was added after
// the table shipped. The table_info check skips the common already-migrated case, but
// during a production build the 8 parallel page-data workers each open this same file
// with no shared connection cache, so two can pass the check and both ALTER — the loser
// throws "duplicate column name". Swallow exactly that error; re-throw anything else.
const briefColumns = db.prepare("PRAGMA table_info(area_briefs)").all() as { name: string }[];
if (!briefColumns.some((column) => column.name === "predict_level")) {
  try {
    db.exec("ALTER TABLE area_briefs ADD COLUMN predict_level INTEGER NOT NULL DEFAULT 0");
  } catch (error) {
    if (!(error instanceof Error && /duplicate column name/i.test(error.message))) {
      throw error;
    }
  }
}

// Migration: `area_id` (the forecast area a villager belongs to, used for area-scoped SMS
// and per-area citizen counts) was added after the villagers table shipped. Same
// parallel-build race as above — swallow only "duplicate column name".
const villagerColumns = db.prepare("PRAGMA table_info(villagers)").all() as { name: string }[];
if (!villagerColumns.some((column) => column.name === "area_id")) {
  try {
    db.exec("ALTER TABLE villagers ADD COLUMN area_id TEXT");
  } catch (error) {
    if (!(error instanceof Error && /duplicate column name/i.test(error.message))) {
      throw error;
    }
  }
}

db.prepare("INSERT OR IGNORE INTO users (username, password_hash, created_at) VALUES (?, ?, ?)").run(
  "admin",
  bcrypt.hashSync("admin123", 12),
  Date.now(),
);
