"use server";

import { revalidatePath } from "next/cache";
import { headers } from "next/headers";

import { getSessionUser } from "@/lib/auth";
import { createEmergencyContact, deleteEmergencyContact } from "@/lib/emergency-contacts";
import { getForecast } from "@/lib/forecast";
import { nearestArea } from "@/lib/geo";
import { geolocateIp, PROVINCE_CENTROID } from "@/lib/geolocate";

export type EmergencyContactFormState = {
  error?: string;
  ok?: boolean;
};

export async function addEmergencyContact(
  _: EmergencyContactFormState,
  formData: FormData,
): Promise<EmergencyContactFormState> {
  // Open to everyone: a logged-in chief owns the number (permanent), an anonymous visitor's
  // number lives 48h. A missing session is not an error here.
  const user = await getSessionUser();

  const name = String(formData.get("name") ?? "").trim();
  const phone = String(formData.get("phone") ?? "").trim();
  const areaId = String(formData.get("areaId") ?? "").trim() || null;

  if (!name) return { error: "Vui lòng nhập tên đơn vị / người phụ trách." };
  if (!phone) return { error: "Vui lòng nhập số điện thoại." };

  // The location used to sort numbers nearest-first for citizens is derived from the adder's
  // IP (the responder is at their own location). Fall back to a picked commune's centroid,
  // then the province centroid, so a contact always has coordinates for the calculation.
  const requestHeaders = await headers();
  const forwardedFor = requestHeaders.get("x-forwarded-for");
  const ip = (forwardedFor ? forwardedFor.split(",")[0]! : requestHeaders.get("x-real-ip") ?? "").trim();
  const ipLocation = await geolocateIp(ip);

  const forecast = await getForecast();
  const areas = forecast?.days[0]?.areas ?? [];
  const picked = areaId ? areas.find((candidate) => candidate.id === areaId) : undefined;

  const coords = ipLocation ?? picked?.coordinates ?? PROVINCE_CENTROID;
  // Label the number with the picked commune, or (when none was picked) the commune nearest
  // the IP-derived coordinates.
  const area = picked ?? nearestArea(coords, areas);

  createEmergencyContact(
    {
      name,
      phone,
      areaId: area?.id ?? null,
      areaName: area?.name ?? null,
      lat: coords.lat,
      lng: coords.lng,
    },
    user?.id ?? null,
  );
  revalidatePath("/rescue");
  return { ok: true };
}

export async function removeEmergencyContact(formData: FormData): Promise<void> {
  // Only a logged-in owner can delete; anonymous numbers age off on their own.
  const user = await getSessionUser();
  if (!user) return;

  const id = Number(formData.get("id"));
  if (Number.isInteger(id) && id > 0) {
    deleteEmergencyContact(user.id, id);
    revalidatePath("/rescue");
  }
}
