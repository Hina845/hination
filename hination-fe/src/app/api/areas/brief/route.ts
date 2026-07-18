import { NextResponse } from "next/server";

import { getAreaBrief } from "@/lib/area-brief";
import { getSessionUser } from "@/lib/auth";
import { logError, logStep } from "@/lib/log";
import type { AreaBriefInput } from "@/types/area-brief";

// better-sqlite3 + outbound fetches require the Node.js runtime, and every hover
// may force a fresh generation, so this must never be statically cached.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RequestBody = AreaBriefInput & { refresh?: boolean };

export async function POST(request: Request) {
  const startedAt = Date.now();
  logStep("api/brief", "POST received");

  const user = await getSessionUser();
  if (!user) {
    logStep("api/brief", "rejected: not signed in → 401");
    return NextResponse.json({ error: "Chưa đăng nhập" }, { status: 401 });
  }

  let body: RequestBody | null = null;
  try {
    body = (await request.json()) as RequestBody;
  } catch {
    body = null;
  }

  if (!body?.areaId || !body?.name || !body?.date) {
    logStep("api/brief", "rejected: missing fields → 400");
    return NextResponse.json({ error: "Thiếu thông tin khu vực" }, { status: 400 });
  }

  logStep("api/brief", "authorized", { user: user.username, area: body.name, refresh: Boolean(body.refresh) });

  try {
    const brief = await getAreaBrief(
      {
        areaId: body.areaId,
        name: body.name,
        adminCode: body.adminCode,
        date: body.date,
        danger: body.danger,
      },
      Boolean(body.refresh),
    );
    logStep("api/brief", "done → 200", { cached: brief.cached, sources: brief.sources.length, ms: Date.now() - startedAt });
    return NextResponse.json(brief);
  } catch (error) {
    logError("api/brief", "failed → 502", error);
    const message = error instanceof Error ? error.message : "Không thể tạo bản tin";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
