import { getSessionUser } from "@/lib/auth";
import { getRecordingAudio } from "@/lib/recordings";

// better-sqlite3 requires the Node.js runtime, and audio is owner-scoped per session, so
// this must never be statically cached.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Stream one saved voice clip back to its owner (the <audio> src in the radio studio).
// 404 for a missing id OR another chief's recording — same response so ownership isn't
// probeable.
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const user = await getSessionUser();
  if (!user) {
    return new Response("Unauthorized", { status: 401 });
  }

  const { id } = await params;
  const recordingId = Number(id);
  if (!Number.isInteger(recordingId) || recordingId <= 0) {
    return new Response("Not found", { status: 404 });
  }

  const clip = getRecordingAudio(user.id, recordingId);
  if (!clip) {
    return new Response("Not found", { status: 404 });
  }

  const body = new Uint8Array(clip.audio);
  return new Response(body, {
    status: 200,
    headers: {
      "Content-Type": clip.mime,
      "Content-Length": String(body.byteLength),
      "Cache-Control": "private, max-age=3600",
      "Accept-Ranges": "none",
    },
  });
}
