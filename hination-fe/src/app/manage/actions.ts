"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";

import { getSessionUser } from "@/lib/auth";
import { logSms } from "@/lib/sms-log";
import { sendEmergencySms } from "@/lib/sms";
import { createVillager, deleteVillager, listVillagers, updateVillager } from "@/lib/villagers";

export type VillagerFormState = {
  error?: string;
  ok?: boolean;
};

export type SmsFormState = {
  error?: string;
  sent?: number;
};

async function requireUserId(): Promise<number> {
  const user = await getSessionUser();
  if (!user) {
    redirect("/login");
  }
  return user.id;
}

function readFields(formData: FormData) {
  const areaId = String(formData.get("areaId") ?? "").trim();
  return {
    name: String(formData.get("name") ?? "").trim(),
    phone: String(formData.get("phone") ?? "").trim(),
    address: String(formData.get("address") ?? "").trim(),
    areaId: areaId || null,
  };
}

// Parse the optional `areaIds` field (a JSON array of forecast area ids) shared by the
// manage modal, the map hover card, and the dangerous-areas blast. Anything unparseable
// or absent means "no area filter" — send to every villager.
function readAreaIds(formData: FormData): string[] {
  const raw = formData.get("areaIds");
  if (typeof raw !== "string" || !raw.trim()) return [];
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed.filter((value): value is string => typeof value === "string");
  } catch {
    return [];
  }
  return [];
}

function validate(fields: { name: string; phone: string }): string | null {
  if (!fields.name) return "Vui lòng nhập họ tên người dân.";
  if (!fields.phone) return "Vui lòng nhập số điện thoại.";
  return null;
}

export async function addVillager(_: VillagerFormState, formData: FormData): Promise<VillagerFormState> {
  const ownerId = await requireUserId();
  const fields = readFields(formData);

  const error = validate(fields);
  if (error) {
    return { error };
  }

  createVillager(ownerId, fields);
  revalidatePath("/manage");
  return { ok: true };
}

export async function editVillager(_: VillagerFormState, formData: FormData): Promise<VillagerFormState> {
  const ownerId = await requireUserId();
  const id = Number(formData.get("id"));
  const fields = readFields(formData);

  if (!Number.isInteger(id) || id <= 0) {
    return { error: "Không tìm thấy người dân cần sửa." };
  }

  const error = validate(fields);
  if (error) {
    return { error };
  }

  const updated = updateVillager(ownerId, id, fields);
  if (!updated) {
    return { error: "Không thể cập nhật. Người dân không tồn tại." };
  }

  revalidatePath("/manage");
  return { ok: true };
}

export async function removeVillager(formData: FormData): Promise<void> {
  const ownerId = await requireUserId();
  const id = Number(formData.get("id"));

  if (Number.isInteger(id) && id > 0) {
    deleteVillager(ownerId, id);
    revalidatePath("/manage");
  }
}

export async function sendSms(_: SmsFormState, formData: FormData): Promise<SmsFormState> {
  const ownerId = await requireUserId();
  const message = String(formData.get("message") ?? "").trim();
  const areaIds = readAreaIds(formData);

  if (!message) {
    return { error: "Vui lòng nhập nội dung tin nhắn." };
  }

  // Empty areaIds = blast to every villager; otherwise only villagers tagged to one of
  // the selected areas. `null`-area villagers are never matched by an area filter.
  const areaSet = new Set(areaIds);
  const recipients = listVillagers(ownerId)
    .filter((villager) => areaSet.size === 0 || (villager.areaId !== null && areaSet.has(villager.areaId)))
    .map((villager) => ({ name: villager.name, phone: villager.phone }));

  if (recipients.length === 0) {
    return {
      error: areaIds.length > 0
        ? "Không có người dân nào trong khu vực đã chọn."
        : "Chưa có người dân nào để gửi tin.",
    };
  }

  const result = await sendEmergencySms(recipients, message);
  logSms(ownerId, { areaIds, message, recipientCount: result.sent });
  // Refresh both the manage history/counter and the map summary window.
  revalidatePath("/manage");
  revalidatePath("/app");
  return { sent: result.sent };
}
