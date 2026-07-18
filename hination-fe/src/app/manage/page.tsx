import { redirect } from "next/navigation";

import ManageSidebar from "@/components/ManageSidebar";
import VillagerManager from "@/components/VillagerManager";
import { getSessionUser } from "@/lib/auth";
import { listVillagers } from "@/lib/villagers";

// better-sqlite3 requires the Node.js runtime, and the villager list is per-session,
// so this screen must never be statically cached.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export default async function ManagePage() {
  const user = await getSessionUser();

  if (!user) {
    redirect("/login");
  }

  const villagers = listVillagers(user.id);

  return (
    <div className="flex min-h-svh bg-[#eef2f6] text-[#0f172a]">
      <ManageSidebar active="manage" />
      <VillagerManager villagers={villagers} />
    </div>
  );
}
