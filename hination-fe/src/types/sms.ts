// Pure type shared between the SMS-log server helpers (src/lib/sms-log) and the client
// manager UI. Keep this file free of server-only imports so it never drags
// better-sqlite3 / node APIs into the client bundle.

export type SmsLog = {
  id: number;
  areaIds: string[]; // targeted forecast area ids; empty = every villager the chief owns
  message: string;
  recipientCount: number;
  createdAt: number; // epoch ms
};
