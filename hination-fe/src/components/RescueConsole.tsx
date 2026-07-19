"use client";

import { Lifebuoy, MapPin, Phone, Trash, Warning } from "@phosphor-icons/react";
import { useActionState, useEffect, useRef, useState } from "react";

import { addEmergencyContact, removeEmergencyContact, type EmergencyContactFormState } from "@/app/rescue/actions";
import type { AreaOption } from "@/types/area";
import type { EmergencyContact } from "@/types/emergency-contact";

// A help request enriched with its resolved commune name (see app/rescue/page.tsx).
export type RescueRequestView = {
  id: number;
  lat: number;
  lng: number;
  reason: string | null;
  place: string | null; // citizen-stated "Tôi đang ở…" location
  source: "gps" | "ip";
  createdAt: number;
  locationName: string | null; // nearest commune, reverse-geocoded from coordinates
};

type Tab = "requests" | "contacts";

function mapsHref(lat: number, lng: number): string {
  return `https://www.google.com/maps?q=${lat},${lng}`;
}

function timeAgo(ms: number): string {
  const diff = Date.now() - ms;
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "vừa xong";
  if (minutes < 60) return `${minutes} phút trước`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} giờ trước`;
  return `${Math.floor(hours / 24)} ngày trước`;
}

const tabClass = (active: boolean) =>
  `h-11 rounded-lg px-5 text-sm font-semibold transition-colors ${
    active ? "bg-[#4f46e5] text-white" : "border border-[#cbd5e1] bg-white text-[#475569] hover:bg-[#f1f5f9]"
  }`;

export default function RescueConsole({
  requests,
  contacts,
  areaOptions,
  isChief,
}: {
  requests: RescueRequestView[];
  contacts: EmergencyContact[];
  areaOptions: AreaOption[];
  isChief: boolean;
}) {
  const [tab, setTab] = useState<Tab>("requests");

  return (
    <main className="flex-1 overflow-y-auto px-6 py-8 md:px-10">
      <header className="mb-6 flex flex-col gap-2">
        <h1 className="flex items-center gap-2.5 text-2xl font-bold text-[#0f172a]">
          <Lifebuoy weight="fill" className="size-7 text-[#ef4444]" />
          Cứu hộ
        </h1>
        <p className="max-w-2xl text-sm text-[#475569]">
          Danh sách người dân đang cần trợ giúp khẩn cấp kèm vị trí, và các số điện thoại cứu hộ hiển thị cho người dân.
        </p>
      </header>

      <div className="mb-6 flex flex-wrap gap-2" data-tour="rescue-tabs">
        <button type="button" className={tabClass(tab === "requests")} onClick={() => setTab("requests")}>
          Yêu cầu cứu trợ ({requests.length})
        </button>
        <button type="button" className={tabClass(tab === "contacts")} onClick={() => setTab("contacts")}>
          Số điện thoại khẩn cấp ({contacts.length})
        </button>
      </div>

      <div data-tour="rescue-requests">
        {tab === "requests" ? (
          <RequestList requests={requests} />
        ) : (
          <ContactsTab contacts={contacts} areaOptions={areaOptions} isChief={isChief} />
        )}
      </div>
    </main>
  );
}

function RequestList({ requests }: { requests: RescueRequestView[] }) {
  if (requests.length === 0) {
    return (
      <p className="rounded-2xl border border-[rgb(15_23_42_/_8%)] bg-white px-6 py-10 text-center text-[#475569]">
        Chưa có yêu cầu cứu trợ nào trong 24 giờ qua.
      </p>
    );
  }

  return (
    <ul className="flex flex-col gap-3">
      {requests.map((request) => (
        <li
          key={request.id}
          className="flex flex-col gap-3 rounded-2xl border border-[rgb(15_23_42_/_8%)] bg-white p-5 shadow-[0_0.75rem_2.25rem_rgb(15_23_42_/_6%)] md:flex-row md:items-start md:justify-between"
        >
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center gap-2 text-lg font-semibold text-[#0f172a]">
              <MapPin weight="fill" className="size-5 text-[#ef4444]" />
              {request.place ?? request.locationName ?? "Vị trí chưa xác định"}
            </div>
            {request.place && request.locationName && (
              <div className="text-sm text-[#475569]">Khu vực: {request.locationName}</div>
            )}
            <div className="text-sm text-[#475569]">
              {request.lat.toFixed(5)}, {request.lng.toFixed(5)}
              <span
                className={`ml-2 rounded-full px-2 py-0.5 text-xs font-semibold ${
                  request.source === "gps" ? "bg-[#dcfce7] text-[#15803d]" : "bg-[#fef3c7] text-[#b45309]"
                }`}
              >
                {request.source === "gps" ? "GPS chính xác" : "Vị trí theo IP"}
              </span>
            </div>
            {request.reason && <p className="text-sm text-[#0f172a]">“{request.reason}”</p>}
            <div className="text-xs text-[#94a3b8]">{timeAgo(request.createdAt)}</div>
          </div>
          <a
            href={mapsHref(request.lat, request.lng)}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-10 shrink-0 items-center justify-center gap-1.5 rounded-lg bg-[#4f46e5] px-4 text-sm font-semibold text-white transition-colors hover:bg-[#4338ca]"
          >
            <MapPin weight="fill" className="size-4" />
            Xem bản đồ
          </a>
        </li>
      ))}
    </ul>
  );
}

function ContactsTab({
  contacts,
  areaOptions,
  isChief,
}: {
  contacts: EmergencyContact[];
  areaOptions: AreaOption[];
  isChief: boolean;
}) {
  const [state, formAction, pending] = useActionState<EmergencyContactFormState, FormData>(addEmergencyContact, {});
  const formRef = useRef<HTMLFormElement>(null);

  useEffect(() => {
    if (state.ok) formRef.current?.reset();
  }, [state.ok]);

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
      <div>
        {contacts.length === 0 ? (
          <p className="rounded-2xl border border-[rgb(15_23_42_/_8%)] bg-white px-6 py-10 text-center text-[#475569]">
            Chưa có số điện thoại khẩn cấp nào.
          </p>
        ) : (
          <ul className="flex flex-col gap-3">
            {contacts.map((contact) => (
              <li
                key={contact.id}
                className="flex items-center justify-between gap-3 rounded-2xl border border-[rgb(15_23_42_/_8%)] bg-white p-4 shadow-[0_0.75rem_2.25rem_rgb(15_23_42_/_6%)]"
              >
                <div className="flex flex-col gap-1">
                  <div className="flex items-center gap-2 font-semibold text-[#0f172a]">
                    <Phone weight="fill" className="size-5 text-[#16a34a]" />
                    {contact.name}
                    {contact.expiresAt !== null && (
                      <span className="rounded-full bg-[#fef3c7] px-2 py-0.5 text-xs font-semibold text-[#b45309]">
                        48h
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-[#475569]">
                    <a href={`tel:${contact.phone}`} className="font-medium text-[#4f46e5]">
                      {contact.phone}
                    </a>
                    {contact.areaName && <span className="ml-2 text-[#94a3b8]">· {contact.areaName}</span>}
                  </div>
                </div>
                {isChief && contact.expiresAt === null && (
                  <form action={removeEmergencyContact}>
                    <input type="hidden" name="id" value={contact.id} />
                    <button
                      type="submit"
                      aria-label="Xóa số điện thoại"
                      className="inline-flex size-9 items-center justify-center rounded-lg border border-[#cbd5e1] text-[#475569] transition-colors hover:bg-[#fef2f2] hover:text-[#dc2626]"
                    >
                      <Trash className="size-4" />
                    </button>
                  </form>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <form
        ref={formRef}
        action={formAction}
        className="flex h-fit flex-col gap-3 rounded-2xl border border-[rgb(15_23_42_/_8%)] bg-white p-5 shadow-[0_0.75rem_2.25rem_rgb(15_23_42_/_6%)]"
      >
        <h2 className="text-lg font-semibold text-[#0f172a]">Thêm số khẩn cấp</h2>
        {!isChief && (
          <p className="rounded-lg bg-[#fef3c7] px-3 py-2 text-xs text-[#b45309]">
            Bạn chưa đăng nhập — số này sẽ tự động xóa sau 48 giờ.
          </p>
        )}
        <label className="flex flex-col gap-1 text-sm font-medium text-[#475569]">
          Tên đơn vị / người phụ trách
          <input
            name="name"
            required
            className="h-10 rounded-lg border border-[#cbd5e1] px-3 text-[#0f172a] outline-none focus:border-[#4f46e5]"
            placeholder="Ví dụ: Trưởng bản, Y tế xã…"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium text-[#475569]">
          Số điện thoại
          <input
            name="phone"
            required
            inputMode="tel"
            className="h-10 rounded-lg border border-[#cbd5e1] px-3 text-[#0f172a] outline-none focus:border-[#4f46e5]"
            placeholder="Ví dụ: 0912345678"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium text-[#475569]">
          Khu vực phụ trách (không bắt buộc)
          <select
            name="areaId"
            defaultValue=""
            className="h-10 rounded-lg border border-[#cbd5e1] px-3 text-[#0f172a] outline-none focus:border-[#4f46e5]"
          >
            <option value="">— Tự động theo vị trí (IP) —</option>
            {areaOptions.map((area) => (
              <option key={area.id} value={area.id}>
                {area.name}
              </option>
            ))}
          </select>
          <span className="text-xs font-normal text-[#94a3b8]">
            Vị trí để sắp xếp “gần nhất” được lấy từ IP của bạn. Chọn khu vực nếu muốn ghi đè.
          </span>
        </label>
        {state.error && (
          <p className="flex items-center gap-1.5 text-sm font-medium text-[#dc2626]">
            <Warning weight="fill" className="size-4" />
            {state.error}
          </p>
        )}
        <button
          type="submit"
          disabled={pending}
          className="h-11 rounded-lg bg-[#4f46e5] font-semibold text-white transition-colors hover:bg-[#4338ca] disabled:opacity-70"
        >
          {pending ? "Đang lưu…" : "Thêm số"}
        </button>
      </form>
    </div>
  );
}
