"use client";

import {
  ChatCircleDots,
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
import type { AreaOption } from "@/types/area";
import type { SmsLog } from "@/types/sms";
import type { Villager } from "@/types/villager";

const emptyFormState: VillagerFormState = {};
const emptySmsState: SmsFormState = {};

// A danger level is "dangerous" at 4+ (mirrors map-theme DANGEROUS_LEVEL) — the default
// floor for the "by danger level" SMS scope.
const DANGEROUS_LEVEL = 4;

// The citizen list can hold tens of thousands of rows (see scripts/seed-citizens.mjs).
// Rendering them all would freeze the table, so we page through 20 at a time; search still
// filters the full list and the counts/stats above reflect it.
const PAGE_SIZE = 20;

function formatSmsTime(ms: number): string {
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(ms));
}

const inputClass =
  "h-12 w-full rounded-[10px] border border-[#cbd5e1] bg-white px-4 text-base text-[#333] outline-none transition-[border-color,box-shadow] duration-150 placeholder:text-[#94a3b8] focus:border-[#6366f1] focus:shadow-[0_0_0_3px_rgb(99_102_241_/_15%)]";

export default function VillagerManager({
  villagers,
  areaOptions = [],
  smsLogs = [],
}: {
  villagers: Villager[];
  areaOptions?: AreaOption[];
  smsLogs?: SmsLog[];
}) {
  const [search, setSearch] = useState("");
  const [areaFilter, setAreaFilter] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Villager | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [showSms, setShowSms] = useState(false);

  const areaNameById = useMemo(
    () => new Map(areaOptions.map((area) => [area.id, area.name])),
    [areaOptions],
  );
  const totalSent = useMemo(() => smsLogs.reduce((sum, log) => sum + log.recipientCount, 0), [smsLogs]);

  const filtered = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return villagers.filter((villager) => {
      // Area filter: "" = all, "__none__" = villagers with no area assigned, otherwise an id.
      if (areaFilter === "__none__") {
        if (villager.areaId) return false;
      } else if (areaFilter && villager.areaId !== areaFilter) {
        return false;
      }
      if (!keyword) return true;
      return (
        villager.name.toLowerCase().includes(keyword) ||
        villager.phone.toLowerCase().includes(keyword) ||
        (villager.address ?? "").toLowerCase().includes(keyword) ||
        (villager.areaId ? (areaNameById.get(villager.areaId) ?? "").toLowerCase().includes(keyword) : false)
      );
    });
  }, [villagers, search, areaFilter, areaNameById]);

  // Jump back to the first page whenever a filter changes so the chief isn't stranded on
  // a now-empty page.
  useEffect(() => {
    setPage(1);
  }, [search, areaFilter]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  // Clamp in case the list shrank (e.g. a delete) before the reset effect runs.
  const currentPage = Math.min(page, totalPages);
  const pageStart = (currentPage - 1) * PAGE_SIZE;
  const pageItems = filtered.slice(pageStart, pageStart + PAGE_SIZE);
  // A small window of page buttons around the current page (±2), so 500 pages don't render
  // 500 buttons.
  const pageWindow: number[] = [];
  for (let p = Math.max(1, currentPage - 2); p <= Math.min(totalPages, currentPage + 2); p += 1) {
    pageWindow.push(p);
  }

  return (
    <main className="flex-1 px-6 py-9 text-base md:px-12">
      <header className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
        <div>
          <h1 className="text-3xl font-bold text-[#0f172a]">Quản lý người dân</h1>
          <p className="mt-2 max-w-2xl text-lg text-[#475569]">
            Thêm số điện thoại và địa chỉ của người dân trong xã để gửi tin nhắn khẩn cấp nhanh chóng khi có thiên tai.
          </p>
        </div>
        <div className="flex shrink-0 gap-3" data-tour="manage-add">
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

      <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between" data-tour="manage-search">
        <div className="flex w-full flex-col gap-3 sm:flex-row sm:items-center">
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
          {areaOptions.length > 0 && (
            <select
              value={areaFilter}
              onChange={(event) => setAreaFilter(event.target.value)}
              aria-label="Lọc theo khu vực"
              className="h-12 w-full rounded-lg border border-[#cbd5e1] bg-white px-4 text-base text-[#333] outline-none transition-[border-color,box-shadow] duration-150 focus:border-[#6366f1] focus:shadow-[0_0_0_3px_rgb(99_102_241_/_15%)] sm:w-56"
            >
              <option value="">Tất cả khu vực</option>
              <option value="__none__">Chưa gán khu vực</option>
              {areaOptions.map((area) => (
                <option key={area.id} value={area.id}>
                  {area.name}
                </option>
              ))}
            </select>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-4 text-base text-[#475569]">
          <span>
            {filtered.length} / {villagers.length} người dân
          </span>
          <span className="inline-flex items-center gap-1.5 text-[#475569]">
            <PaperPlaneTilt size={18} className="text-[#94a3b8]" />
            Đã gửi {totalSent} tin
          </span>
        </div>
      </div>

      <div className="mt-5 overflow-hidden rounded-2xl border border-[rgb(15_23_42_/_8%)] bg-white shadow-[0_0.75rem_2.25rem_rgb(15_23_42_/_6%)]" data-tour="manage-table">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] border-collapse text-left text-base">
            <thead>
              <tr className="border-b border-[#eef2f6] text-sm font-semibold tracking-wide text-[#64748b] uppercase">
                <th className="px-6 py-4 font-semibold">Tên</th>
                <th className="px-6 py-4 font-semibold">Số điện thoại</th>
                <th className="px-6 py-4 font-semibold">Khu vực</th>
                <th className="px-6 py-4 font-semibold">Địa chỉ</th>
                <th className="px-6 py-4 text-right font-semibold">Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-16 text-center">
                    <UsersThree size={48} weight="thin" className="mx-auto text-[#cbd5e1]" />
                    <p className="mt-4 text-lg text-[#475569]">
                      {villagers.length === 0
                        ? "Chưa có người dân nào. Nhấn “Thêm người dân” để bắt đầu."
                        : "Không tìm thấy người dân phù hợp."}
                    </p>
                  </td>
                </tr>
              ) : (
                pageItems.map((villager) => (
                  <tr key={villager.id} className="border-b border-[#f1f5f9] last:border-0 hover:bg-[#f8fafc]">
                    <td className="px-6 py-4 text-base font-medium text-[#0f172a]">{villager.name}</td>
                    <td className="px-6 py-4 text-base text-[#334155]">
                      <span className="inline-flex items-center gap-2">
                        <Phone size={18} className="text-[#94a3b8]" />
                        {villager.phone}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-base text-[#475569]">
                      {villager.areaId && areaNameById.has(villager.areaId) ? (
                        areaNameById.get(villager.areaId)
                      ) : (
                        <span className="text-[#cbd5e1]">—</span>
                      )}
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
        {filtered.length > 0 && (
          <div className="flex flex-col gap-3 border-t border-[#f1f5f9] px-6 py-3 text-sm text-[#64748b] sm:flex-row sm:items-center sm:justify-between">
            <span>
              {pageStart + 1}–{Math.min(pageStart + PAGE_SIZE, filtered.length)} / {filtered.length} người dân
            </span>
            {totalPages > 1 && (
              <nav className="flex items-center gap-1" aria-label="Phân trang">
                <button
                  type="button"
                  onClick={() => setPage(currentPage - 1)}
                  disabled={currentPage === 1}
                  className="h-9 rounded-lg border border-[#cbd5e1] bg-white px-3 font-semibold text-[#475569] transition-colors hover:bg-[#f1f5f9] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Trước
                </button>
                {pageWindow[0] > 1 && (
                  <>
                    <button
                      type="button"
                      onClick={() => setPage(1)}
                      className="grid h-9 min-w-9 place-items-center rounded-lg border border-[#cbd5e1] bg-white px-2 font-semibold text-[#475569] transition-colors hover:bg-[#f1f5f9]"
                    >
                      1
                    </button>
                    {pageWindow[0] > 2 && <span className="px-1 text-[#94a3b8]">…</span>}
                  </>
                )}
                {pageWindow.map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setPage(p)}
                    aria-current={p === currentPage ? "page" : undefined}
                    className={`grid h-9 min-w-9 place-items-center rounded-lg border px-2 font-semibold transition-colors ${
                      p === currentPage
                        ? "border-[#4f46e5] bg-[#4f46e5] text-white"
                        : "border-[#cbd5e1] bg-white text-[#475569] hover:bg-[#f1f5f9]"
                    }`}
                  >
                    {p}
                  </button>
                ))}
                {pageWindow[pageWindow.length - 1] < totalPages && (
                  <>
                    {pageWindow[pageWindow.length - 1] < totalPages - 1 && <span className="px-1 text-[#94a3b8]">…</span>}
                    <button
                      type="button"
                      onClick={() => setPage(totalPages)}
                      className="grid h-9 min-w-9 place-items-center rounded-lg border border-[#cbd5e1] bg-white px-2 font-semibold text-[#475569] transition-colors hover:bg-[#f1f5f9]"
                    >
                      {totalPages}
                    </button>
                  </>
                )}
                <button
                  type="button"
                  onClick={() => setPage(currentPage + 1)}
                  disabled={currentPage === totalPages}
                  className="h-9 rounded-lg border border-[#cbd5e1] bg-white px-3 font-semibold text-[#475569] transition-colors hover:bg-[#f1f5f9] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Sau
                </button>
              </nav>
            )}
          </div>
        )}
      </div>

      {/* SMS history — every emergency blast the chief has sent, newest first. */}
      <section className="mt-10">
        <h2 className="text-xl font-bold text-[#0f172a]">Tin nhắn đã gửi</h2>
        <div className="mt-4 overflow-hidden rounded-2xl border border-[rgb(15_23_42_/_8%)] bg-white shadow-[0_0.75rem_2.25rem_rgb(15_23_42_/_6%)]">
          {smsLogs.length === 0 ? (
            <div className="px-6 py-12 text-center">
              <ChatCircleDots size={44} weight="thin" className="mx-auto text-[#cbd5e1]" />
              <p className="mt-3 text-base text-[#475569]">Chưa gửi tin nhắn nào.</p>
            </div>
          ) : (
            <ul className="divide-y divide-[#f1f5f9]">
              {smsLogs.map((log) => {
                const scope =
                  log.areaIds.length === 0
                    ? "Tất cả người dân"
                    : log.areaIds.map((id) => areaNameById.get(id) ?? id).join(", ");
                return (
                  <li key={log.id} className="px-6 py-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="inline-flex items-center gap-2 text-sm font-semibold text-[#0f172a]">
                        <MapPin size={16} className="text-[#94a3b8]" />
                        {scope}
                      </span>
                      <span className="text-sm text-[#64748b]">
                        {formatSmsTime(log.createdAt)} · {log.recipientCount} người
                      </span>
                    </div>
                    <p className="mt-1.5 line-clamp-2 text-base text-[#475569] whitespace-pre-line">{log.message}</p>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </section>

      {showAdd && <VillagerFormModal mode="add" areaOptions={areaOptions} onClose={() => setShowAdd(false)} />}
      {editing && <VillagerFormModal mode="edit" villager={editing} areaOptions={areaOptions} onClose={() => setEditing(null)} />}
      {showSms && (
        <SmsModal villagers={villagers} areaOptions={areaOptions} onClose={() => setShowSms(false)} />
      )}
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
  areaOptions,
  onClose,
}: {
  mode: "add" | "edit";
  villager?: Villager;
  areaOptions: AreaOption[];
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
          <label htmlFor="villager-area" className="text-base font-semibold text-[#475569]">
            Khu vực <span className="font-normal text-[#94a3b8]">(không bắt buộc)</span>
          </label>
          <select
            id="villager-area"
            name="areaId"
            defaultValue={villager?.areaId ?? ""}
            className={inputClass}
          >
            <option value="">— Chưa gán khu vực —</option>
            {areaOptions.map((area) => (
              <option key={area.id} value={area.id}>
                {area.name}
              </option>
            ))}
          </select>
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

type SmsScope = "all" | "areas" | "level";

function SmsModal({
  villagers,
  areaOptions,
  onClose,
}: {
  villagers: Villager[];
  areaOptions: AreaOption[];
  onClose: () => void;
}) {
  const [state, formAction, isPending] = useActionState(sendSms, emptySmsState);
  const [scope, setScope] = useState<SmsScope>("all");
  const [selectedAreas, setSelectedAreas] = useState<Set<string>>(new Set());
  const [minLevel, setMinLevel] = useState(DANGEROUS_LEVEL);

  // Villager count per area from the authoritative list, so the recipient preview matches
  // exactly what the server action will send.
  const countByArea = useMemo(() => {
    const counts = new Map<string, number>();
    for (const villager of villagers) {
      if (villager.areaId) counts.set(villager.areaId, (counts.get(villager.areaId) ?? 0) + 1);
    }
    return counts;
  }, [villagers]);

  // Areas the current scope targets. "all" → empty array (server sends to everyone).
  const targetAreaIds = useMemo(() => {
    if (scope === "areas") return Array.from(selectedAreas);
    if (scope === "level") return areaOptions.filter((area) => area.level >= minLevel).map((area) => area.id);
    return [];
  }, [scope, selectedAreas, minLevel, areaOptions]);

  const recipientCount = useMemo(() => {
    if (scope === "all") return villagers.length;
    return targetAreaIds.reduce((sum, id) => sum + (countByArea.get(id) ?? 0), 0);
  }, [scope, villagers.length, targetAreaIds, countByArea]);

  const toggleArea = (id: string) =>
    setSelectedAreas((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const tabClass = (active: boolean) =>
    `h-10 rounded-lg px-4 text-sm font-semibold transition-colors ${
      active ? "bg-[#4f46e5] text-white" : "border border-[#cbd5e1] bg-white text-[#475569] hover:bg-[#f1f5f9]"
    }`;

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
          <div className="grid gap-2">
            <span className="text-base font-semibold text-[#475569]">Người nhận</span>
            <div className="flex flex-wrap gap-2">
              <button type="button" className={tabClass(scope === "all")} onClick={() => setScope("all")}>
                Tất cả
              </button>
              <button type="button" className={tabClass(scope === "areas")} onClick={() => setScope("areas")}>
                Chọn khu vực
              </button>
              <button type="button" className={tabClass(scope === "level")} onClick={() => setScope("level")}>
                Theo mức độ
              </button>
            </div>
          </div>

          {scope === "areas" && (
            <div className="grid max-h-48 gap-1 overflow-y-auto rounded-lg border border-[#e2e8f0] p-2">
              {areaOptions.length === 0 ? (
                <p className="px-2 py-3 text-sm text-[#94a3b8]">Không có dữ liệu khu vực.</p>
              ) : (
                areaOptions.map((area) => (
                  <label key={area.id} className="flex items-center gap-3 rounded-md px-2 py-1.5 text-base hover:bg-[#f8fafc]">
                    <input
                      type="checkbox"
                      checked={selectedAreas.has(area.id)}
                      onChange={() => toggleArea(area.id)}
                      className="size-4"
                    />
                    <span className="flex-1 text-[#334155]">{area.name}</span>
                    <span className="text-sm text-[#94a3b8]">{countByArea.get(area.id) ?? 0} người</span>
                  </label>
                ))
              )}
            </div>
          )}

          {scope === "level" && (
            <div className="grid gap-2 rounded-lg border border-[#e2e8f0] p-3">
              <label htmlFor="sms-min-level" className="text-sm font-semibold text-[#475569]">
                Gửi tới khu vực từ cấp {minLevel} trở lên
              </label>
              <input
                id="sms-min-level"
                type="range"
                min={1}
                max={5}
                step={1}
                value={minLevel}
                onChange={(event) => setMinLevel(Number(event.target.value))}
                className="w-full"
              />
              <span className="text-sm text-[#64748b]">{targetAreaIds.length} khu vực phù hợp</span>
            </div>
          )}

          <p className="text-base text-[#475569]">
            Tin nhắn sẽ được gửi tới <strong className="text-[#0f172a]">{recipientCount} người dân</strong>.
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

          <input type="hidden" name="areaIds" value={JSON.stringify(targetAreaIds)} />

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
              disabled={isPending || recipientCount === 0}
              className="inline-flex h-12 items-center gap-2 rounded-lg bg-[#4f46e5] px-6 text-base font-semibold text-white transition-colors hover:bg-[#4338ca] disabled:cursor-not-allowed disabled:opacity-70"
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
