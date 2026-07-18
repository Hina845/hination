"use client";

import {
  MagnifyingGlass,
  MapPin,
  PaperPlaneTilt,
  PencilSimple,
  Phone,
  Plus,
  Trash,
  UsersThree,
  X,
} from "@phosphor-icons/react";
import { useActionState, useEffect, useMemo, useState } from "react";

import {
  addVillager,
  editVillager,
  removeVillager,
  sendSms,
  type SmsFormState,
  type VillagerFormState,
} from "@/app/manage/actions";
import type { Villager } from "@/types/villager";

const emptyFormState: VillagerFormState = {};
const emptySmsState: SmsFormState = {};

const inputClass =
  "h-12 w-full rounded-[10px] border border-[#cbd5e1] bg-white px-4 text-base text-[#333] outline-none transition-[border-color,box-shadow] duration-150 placeholder:text-[#94a3b8] focus:border-[#6366f1] focus:shadow-[0_0_0_3px_rgb(99_102_241_/_15%)]";

export default function VillagerManager({ villagers }: { villagers: Villager[] }) {
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<Villager | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [showSms, setShowSms] = useState(false);

  const filtered = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    if (!keyword) return villagers;
    return villagers.filter(
      (villager) =>
        villager.name.toLowerCase().includes(keyword) ||
        villager.phone.toLowerCase().includes(keyword) ||
        (villager.address ?? "").toLowerCase().includes(keyword),
    );
  }, [villagers, search]);

  return (
    <main className="flex-1 px-6 py-9 text-base md:px-12">
      <header className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
        <div>
          <h1 className="text-3xl font-bold text-[#0f172a]">Quản lý người dân</h1>
          <p className="mt-2 max-w-2xl text-lg text-[#475569]">
            Thêm số điện thoại và địa chỉ của người dân trong xã để gửi tin nhắn khẩn cấp nhanh chóng khi có thiên tai.
          </p>
        </div>
        <div className="flex shrink-0 gap-3">
          <button
            type="button"
            onClick={() => setShowAdd(true)}
            className="inline-flex h-12 items-center gap-2 rounded-lg bg-[#4f46e5] px-5 text-base font-semibold text-white shadow-sm transition-colors hover:bg-[#4338ca]"
          >
            <Plus weight="bold" size={20} /> Thêm người dân
          </button>
          <button
            type="button"
            onClick={() => setShowSms(true)}
            className="inline-flex h-12 items-center gap-2 rounded-lg border border-[#cbd5e1] bg-white px-5 text-base font-semibold text-[#0f172a] transition-colors hover:bg-[#f1f5f9]"
          >
            <PaperPlaneTilt weight="fill" size={20} /> Gửi SMS khẩn
          </button>
        </div>
      </header>

      <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative w-full max-w-md">
          <MagnifyingGlass
            size={20}
            className="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-[#94a3b8]"
          />
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Tìm theo tên, số điện thoại, địa chỉ"
            aria-label="Tìm người dân"
            className="h-12 w-full rounded-lg border border-[#cbd5e1] bg-white pr-4 pl-11 text-base text-[#333] outline-none transition-[border-color,box-shadow] duration-150 placeholder:text-[#94a3b8] focus:border-[#6366f1] focus:shadow-[0_0_0_3px_rgb(99_102_241_/_15%)]"
          />
        </div>
        <span className="text-base text-[#475569]">
          {filtered.length} / {villagers.length} người dân
        </span>
      </div>

      <div className="mt-5 overflow-hidden rounded-2xl border border-[rgb(15_23_42_/_8%)] bg-white shadow-[0_0.75rem_2.25rem_rgb(15_23_42_/_6%)]">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] border-collapse text-left text-base">
            <thead>
              <tr className="border-b border-[#eef2f6] text-sm font-semibold tracking-wide text-[#64748b] uppercase">
                <th className="px-6 py-4 font-semibold">Tên</th>
                <th className="px-6 py-4 font-semibold">Số điện thoại</th>
                <th className="px-6 py-4 font-semibold">Địa chỉ</th>
                <th className="px-6 py-4 text-right font-semibold">Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-6 py-16 text-center">
                    <UsersThree size={48} weight="thin" className="mx-auto text-[#cbd5e1]" />
                    <p className="mt-4 text-lg text-[#475569]">
                      {villagers.length === 0
                        ? "Chưa có người dân nào. Nhấn “Thêm người dân” để bắt đầu."
                        : "Không tìm thấy người dân phù hợp."}
                    </p>
                  </td>
                </tr>
              ) : (
                filtered.map((villager) => (
                  <tr key={villager.id} className="border-b border-[#f1f5f9] last:border-0 hover:bg-[#f8fafc]">
                    <td className="px-6 py-4 text-base font-medium text-[#0f172a]">{villager.name}</td>
                    <td className="px-6 py-4 text-base text-[#334155]">
                      <span className="inline-flex items-center gap-2">
                        <Phone size={18} className="text-[#94a3b8]" />
                        {villager.phone}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-base text-[#475569]">
                      {villager.address ? (
                        <span className="inline-flex items-center gap-2">
                          <MapPin size={18} className="text-[#94a3b8]" />
                          {villager.address}
                        </span>
                      ) : (
                        <span className="text-[#cbd5e1]">—</span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => setEditing(villager)}
                          aria-label={`Sửa ${villager.name}`}
                          className="grid size-10 place-items-center rounded-lg text-[#475569] transition-colors hover:bg-[#eef2ff] hover:text-[#4f46e5]"
                        >
                          <PencilSimple size={20} />
                        </button>
                        <form
                          action={removeVillager}
                          onSubmit={(event) => {
                            if (!window.confirm(`Xóa người dân “${villager.name}”?`)) {
                              event.preventDefault();
                            }
                          }}
                        >
                          <input type="hidden" name="id" value={villager.id} />
                          <button
                            type="submit"
                            aria-label={`Xóa ${villager.name}`}
                            className="grid size-10 place-items-center rounded-lg text-[#475569] transition-colors hover:bg-[#fef2f2] hover:text-[#ef4444]"
                          >
                            <Trash size={20} />
                          </button>
                        </form>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {showAdd && <VillagerFormModal mode="add" onClose={() => setShowAdd(false)} />}
      {editing && <VillagerFormModal mode="edit" villager={editing} onClose={() => setEditing(null)} />}
      {showSms && <SmsModal recipientCount={villagers.length} onClose={() => setShowSms(false)} />}
    </main>
  );
}

function ModalShell({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[1000] grid place-items-center bg-[rgb(15_23_42_/_45%)] p-4 text-base"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-lg rounded-2xl bg-white p-7 shadow-[0_1.5rem_3rem_rgb(15_23_42_/_25%)]">
        <div className="mb-5 flex items-center justify-between">
          <h2 className="text-2xl font-bold text-[#0f172a]">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Đóng"
            className="grid size-10 place-items-center rounded-lg text-[#94a3b8] transition-colors hover:bg-[#f1f5f9] hover:text-[#0f172a]"
          >
            <X size={22} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function VillagerFormModal({
  mode,
  villager,
  onClose,
}: {
  mode: "add" | "edit";
  villager?: Villager;
  onClose: () => void;
}) {
  const action = mode === "edit" ? editVillager : addVillager;
  const [state, formAction, isPending] = useActionState(action, emptyFormState);

  useEffect(() => {
    if (state.ok) onClose();
  }, [state.ok, onClose]);

  return (
    <ModalShell title={mode === "edit" ? "Sửa thông tin người dân" : "Thêm người dân"} onClose={onClose}>
      <form action={formAction} className="grid gap-4" noValidate>
        {mode === "edit" && villager && <input type="hidden" name="id" value={villager.id} />}

        <div className="grid gap-2">
          <label htmlFor="villager-name" className="text-base font-semibold text-[#475569]">
            Họ tên
          </label>
          <input
            id="villager-name"
            name="name"
            defaultValue={villager?.name}
            placeholder="Nguyễn Văn A"
            required
            className={inputClass}
          />
        </div>

        <div className="grid gap-2">
          <label htmlFor="villager-phone" className="text-base font-semibold text-[#475569]">
            Số điện thoại
          </label>
          <input
            id="villager-phone"
            name="phone"
            type="tel"
            inputMode="tel"
            defaultValue={villager?.phone}
            placeholder="09xx xxx xxx"
            required
            className={inputClass}
          />
        </div>

        <div className="grid gap-2">
          <label htmlFor="villager-address" className="text-base font-semibold text-[#475569]">
            Địa chỉ <span className="font-normal text-[#94a3b8]">(không bắt buộc)</span>
          </label>
          <input
            id="villager-address"
            name="address"
            defaultValue={villager?.address ?? ""}
            placeholder="Bản/Tổ, xã…"
            className={inputClass}
          />
        </div>

        <p aria-live="polite" role="status" className="min-h-[22px] text-base text-[#dc2626]">
          {state.error}
        </p>

        <div className="mt-1 flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="h-12 rounded-lg border border-[#cbd5e1] bg-white px-5 text-base font-semibold text-[#475569] transition-colors hover:bg-[#f1f5f9]"
          >
            Hủy
          </button>
          <button
            type="submit"
            disabled={isPending}
            className="h-12 rounded-lg bg-[#4f46e5] px-6 text-base font-semibold text-white transition-colors hover:bg-[#4338ca] disabled:cursor-wait disabled:opacity-70"
          >
            {isPending ? "Đang lưu…" : "Lưu"}
          </button>
        </div>
      </form>
    </ModalShell>
  );
}

function SmsModal({ recipientCount, onClose }: { recipientCount: number; onClose: () => void }) {
  const [state, formAction, isPending] = useActionState(sendSms, emptySmsState);

  return (
    <ModalShell title="Gửi SMS khẩn" onClose={onClose}>
      {typeof state.sent === "number" ? (
        <div className="grid gap-5">
          <div className="grid gap-3 rounded-2xl bg-[#f0fdf4] p-5 text-center">
            <PaperPlaneTilt weight="fill" size={34} className="mx-auto text-[#16a34a]" />
            <p className="text-lg font-semibold text-[#15803d]">Đã gửi tới {state.sent} người dân.</p>
          </div>
          <div className="flex justify-end">
            <button
              type="button"
              onClick={onClose}
              className="h-12 rounded-lg bg-[#4f46e5] px-6 text-base font-semibold text-white transition-colors hover:bg-[#4338ca]"
            >
              Xong
            </button>
          </div>
        </div>
      ) : (
        <form action={formAction} className="grid gap-4" noValidate>
          <p className="text-base text-[#475569]">
            Tin nhắn sẽ được gửi tới <strong className="text-[#0f172a]">{recipientCount} người dân</strong> trong danh
            sách.
          </p>
          <div className="grid gap-2">
            <label htmlFor="sms-message" className="text-base font-semibold text-[#475569]">
              Nội dung tin nhắn
            </label>
            <textarea
              id="sms-message"
              name="message"
              rows={4}
              required
              placeholder="VD: Cảnh báo lũ quét. Người dân di chuyển đến nơi cao, an toàn ngay."
              className="w-full rounded-[10px] border border-[#cbd5e1] bg-white px-4 py-3 text-base text-[#333] outline-none transition-[border-color,box-shadow] duration-150 placeholder:text-[#94a3b8] focus:border-[#6366f1] focus:shadow-[0_0_0_3px_rgb(99_102_241_/_15%)]"
            />
          </div>

          <p aria-live="polite" role="status" className="min-h-[22px] text-base text-[#dc2626]">
            {state.error}
          </p>

          <div className="flex justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="h-12 rounded-lg border border-[#cbd5e1] bg-white px-5 text-base font-semibold text-[#475569] transition-colors hover:bg-[#f1f5f9]"
            >
              Hủy
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="inline-flex h-12 items-center gap-2 rounded-lg bg-[#4f46e5] px-6 text-base font-semibold text-white transition-colors hover:bg-[#4338ca] disabled:cursor-wait disabled:opacity-70"
            >
              <PaperPlaneTilt weight="fill" size={20} />
              {isPending ? "Đang gửi…" : "Gửi ngay"}
            </button>
          </div>
        </form>
      )}
    </ModalShell>
  );
}
