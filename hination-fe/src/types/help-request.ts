// Pure type shared between the help-request server helpers (src/lib/help-requests) and the
// client map layer. Keep this file free of server-only imports so it never drags
// better-sqlite3 / node APIs into the client bundle.

export type HelpRequestSource = "gps" | "ip";

export type HelpRequest = {
  id: number;
  lat: number;
  lng: number;
  reason: string | null;
  source: HelpRequestSource; // 'gps' = precise browser location, 'ip' = IP/centroid fallback
  createdAt: number; // epoch ms
};
