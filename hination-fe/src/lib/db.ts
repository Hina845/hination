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

globalForDatabase.hinationDatabase = db;

db.pragma("journal_mode = WAL");
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
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
  );

  CREATE INDEX IF NOT EXISTS villagers_owner_idx ON villagers(owner_user_id);

  CREATE INDEX IF NOT EXISTS area_briefs_date_idx ON area_briefs(brief_date);
`);

// Migration: `predict_level` (AI news-based danger prediction, 0–2) was added after
// the table shipped. ADD COLUMN is a no-op-safe guard behind a table_info check.
try {
  const briefColumns = db.prepare("PRAGMA table_info(area_briefs)").all() as { name: string }[];
  if (!briefColumns.some((column) => column.name === "predict_level")) {
    db.exec("ALTER TABLE area_briefs ADD COLUMN predict_level INTEGER NOT NULL DEFAULT 0");
  }
} catch {
  // Column may already exist in older databases
}

db.prepare("INSERT OR IGNORE INTO users (username, password_hash, created_at) VALUES (?, ?, ?)").run(
  "admin",
  bcrypt.hashSync("admin123", 12),
  Date.now(),
);
