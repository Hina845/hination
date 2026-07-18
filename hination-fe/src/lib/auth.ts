import { createHash, randomBytes } from "node:crypto";

import bcrypt from "bcryptjs";
import { cookies } from "next/headers";

import { db } from "@/lib/db";

const SESSION_COOKIE = "hination_session";
const SESSION_DURATION_SECONDS = 60 * 60 * 24;

type DatabaseUser = {
  id: number;
  username: string;
  password_hash: string;
};

export type SessionUser = {
  id: number;
  username: string;
};

function hashToken(token: string) {
  return createHash("sha256").update(token).digest("hex");
}

export function authenticate(username: string, password: string): SessionUser | null {
  const user = db
    .prepare("SELECT id, username, password_hash FROM users WHERE username = ?")
    .get(username) as DatabaseUser | undefined;

  if (!user || !bcrypt.compareSync(password, user.password_hash)) {
    return null;
  }

  return { id: user.id, username: user.username };
}

export async function createSession(userId: number) {
  const token = randomBytes(32).toString("base64url");
  const expiresAt = Date.now() + SESSION_DURATION_SECONDS * 1000;

  db.prepare("DELETE FROM sessions WHERE expires_at <= ?").run(Date.now());
  db.prepare("INSERT INTO sessions (user_id, token_hash, expires_at, created_at) VALUES (?, ?, ?, ?)").run(
    userId,
    hashToken(token),
    expiresAt,
    Date.now(),
  );

  const cookieStore = await cookies();
  cookieStore.set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: SESSION_DURATION_SECONDS,
  });
}

export async function getSessionUser(): Promise<SessionUser | null> {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;

  if (!token) {
    return null;
  }

  const session = db
    .prepare(
      `SELECT users.id, users.username, sessions.expires_at
       FROM sessions
       JOIN users ON users.id = sessions.user_id
       WHERE sessions.token_hash = ?`,
    )
    .get(hashToken(token)) as { id: number; username: string; expires_at: number } | undefined;

  if (!session || session.expires_at <= Date.now()) {
    return null;
  }

  return { id: session.id, username: session.username };
}
