// Pure type shared between the server helpers (src/lib/villagers) and the client
// manager (src/components/VillagerManager). Keep this file free of any server-only
// imports so it never drags better-sqlite3 / node APIs into the client bundle.

export type Villager = {
  id: number;
  name: string;
  phone: string;
  address: string | null;
  createdAt: number; // epoch ms
};
