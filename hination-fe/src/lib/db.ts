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
`);

db.prepare("INSERT OR IGNORE INTO users (username, password_hash, created_at) VALUES (?, ?, ?)").run(
  "admin",
  bcrypt.hashSync("admin123", 12),
  Date.now(),
);
