"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";

import { getSessionUser } from "@/lib/auth";
import { createBroadcast, deleteBroadcast } from "@/lib/broadcasts";
import { createRecording, deleteRecording, renameRecording } from "@/lib/recordings";
import { logSms } from "@/lib/sms-log";
import { sendEmergencySms } from "@/lib/sms";
import { listVillagers } from "@/lib/villagers";
import type { BroadcastChannel, BroadcastStatus, BroadcastVoice } from "@/types/broadcast";

// Cap on the stored clip: MediaRecorder audio is small, but reject anything unreasonable
// so a bad client can't push a huge blob into SQLite. 8 MB ≈ several minutes of Opus.
const MAX_RECORDING_BYTES = 8 * 1024 * 1024;

export type RecordingFormState = {
  error?: string;
  savedId?: number;
};

export type BroadcastFormState = {
  error?: string;
  status?: BroadcastStatus; // "draft" | "sent" | "scheduled" — set on success
  recipientCount?: number;
  channelCount?: number;
};

async function requireUserId(): Promise<number> {
  const user = await getSessionUser();
  if (!user) {
    redirect("/login");
  }
  return user.id;
}

const CHANNELS: BroadcastChannel[] = ["loudspeaker", "sms", "zalo"];

function readStringArray(formData: FormData, field: string): string[] {
  const raw = formData.get(field);
  if (typeof raw !== "string" || !raw.trim()) return [];
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed.filter((value): value is string => typeof value === "string");
  } catch {
    return [];
  }
  return [];
}

function readVoice(formData: FormData): BroadcastVoice {
  const raw = formData.get("voice");
  if (typeof raw === "string") {
    try {
      const parsed = JSON.parse(raw) as BroadcastVoice;
      if (parsed?.kind === "recording" && Number.isInteger(parsed.recordingId)) return parsed;
      if (parsed?.kind === "tts" && (parsed.id === "kinh" || parsed.id === "hmong")) return parsed;
    } catch {
      /* fall through */
    }
  }
  return { kind: "tts", id: "kinh" };
}

// Recipients for the SMS channel: villagers tagged to one of the target areas, or every
// villager when no area filter is set. Mirrors sendSms in app/manage/actions.ts.
function recipientsFor(ownerId: number, areaIds: string[]) {
  const areaSet = new Set(areaIds);
  return listVillagers(ownerId)
    .filter((villager) => areaSet.size === 0 || (villager.areaId !== null && areaSet.has(villager.areaId)))
    .map((villager) => ({ name: villager.name, phone: villager.phone }));
}

/**
 * Compose action for the radio studio. `intent` is "draft" (save for later) or "send"
 * (broadcast now / schedule). Sending fans out to the selected channels — the SMS channel
 * reuses the real SMS stub + log; loudspeaker/Zalo are simulated at this stage.
 */
export async function submitBroadcast(
  _: BroadcastFormState,
  formData: FormData,
): Promise<BroadcastFormState> {
  const ownerId = await requireUserId();

  const intent = String(formData.get("intent") ?? "send");
  const message = String(formData.get("message") ?? "").trim();
  const areaIds = readStringArray(formData, "areaIds");
  const requestedChannels = readStringArray(formData, "channels");
  const channels = CHANNELS.filter((channel) => requestedChannels.includes(channel));
  const voice = readVoice(formData);
  const repeat = Math.max(1, Math.min(5, Number(formData.get("repeat")) || 1));
  const repeatGapMinutes = Math.max(0, Math.min(60, Number(formData.get("repeatGapMinutes")) || 0));
  const scheduledAtRaw = Number(formData.get("scheduledAt"));
  const scheduledAt = Number.isFinite(scheduledAtRaw) && scheduledAtRaw > 0 ? scheduledAtRaw : null;

  if (!message) {
    return { error: "Vui lòng nhập nội dung cảnh báo." };
  }
  if (intent === "send" && channels.length === 0) {
    return { error: "Chọn ít nhất một kênh phát." };
  }

  const recipients = recipientsFor(ownerId, areaIds);

  if (intent === "draft") {
    createBroadcast(ownerId, {
      status: "draft",
      areaIds,
      message,
      channels,
      voice,
      repeat,
      repeatGapMinutes,
      scheduledAt,
      recipientCount: recipients.length,
    });
    revalidatePath("/radio");
    return { status: "draft" };
  }

  // Actually broadcast. Only the SMS channel has a real (stubbed) transport today; sending
  // it also records an sms_logs row so the map/manage counters stay in sync.
  let smsSent = 0;
  if (channels.includes("sms")) {
    if (recipients.length === 0) {
      return {
        error: areaIds.length > 0
          ? "Không có người dân nào trong khu vực đã chọn để gửi SMS."
          : "Chưa có người dân nào để gửi SMS.",
      };
    }
    const result = await sendEmergencySms(recipients, message);
    smsSent = result.sent;
    logSms(ownerId, { areaIds, message, recipientCount: smsSent });
  }

  const status: BroadcastStatus = scheduledAt ? "scheduled" : "sent";
  createBroadcast(ownerId, {
    status,
    areaIds,
    message,
    channels,
    voice,
    repeat,
    repeatGapMinutes,
    scheduledAt,
    recipientCount: recipients.length,
  });

  revalidatePath("/radio");
  revalidatePath("/manage");
  revalidatePath("/app");
  return { status, recipientCount: recipients.length, channelCount: channels.length };
}

export async function removeBroadcast(formData: FormData): Promise<void> {
  const ownerId = await requireUserId();
  const id = Number(formData.get("id"));
  if (Number.isInteger(id) && id > 0) {
    deleteBroadcast(ownerId, id);
    revalidatePath("/radio");
  }
}

/** Persist a captured voice clip (multipart form: `audio` blob + `name` + `durationMs`). */
export async function saveRecording(
  _: RecordingFormState,
  formData: FormData,
): Promise<RecordingFormState> {
  const ownerId = await requireUserId();

  const name = String(formData.get("name") ?? "").trim();
  if (!name) return { error: "Vui lòng đặt tên cho bản ghi." };

  const file = formData.get("audio");
  if (!(file instanceof File) || file.size === 0) {
    return { error: "Không nhận được dữ liệu ghi âm. Vui lòng thu lại." };
  }
  if (file.size > MAX_RECORDING_BYTES) {
    return { error: "Bản ghi quá dài. Vui lòng thu ngắn hơn." };
  }

  const durationMs = Math.max(0, Math.round(Number(formData.get("durationMs")) || 0));
  const mime = file.type || "audio/webm";
  const audio = Buffer.from(await file.arrayBuffer());

  const saved = createRecording(ownerId, { name, mime, audio, durationMs });
  revalidatePath("/radio");
  return { savedId: saved.id };
}

export async function renameRecordingAction(formData: FormData): Promise<void> {
  const ownerId = await requireUserId();
  const id = Number(formData.get("id"));
  const name = String(formData.get("name") ?? "").trim();
  if (Number.isInteger(id) && id > 0 && name) {
    renameRecording(ownerId, id, name);
    revalidatePath("/radio");
  }
}

export async function removeRecording(formData: FormData): Promise<void> {
  const ownerId = await requireUserId();
  const id = Number(formData.get("id"));
  if (Number.isInteger(id) && id > 0) {
    deleteRecording(ownerId, id);
    revalidatePath("/radio");
  }
}
