import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import VillagerManager from "@/components/VillagerManager";
import type { AreaOption } from "@/types/area";
import type { SmsLog } from "@/types/sms";
import type { Villager } from "@/types/villager";

// The manager imports server actions, which pull in better-sqlite3. Stub the module
// so the component can render in jsdom without touching the server pipeline.
vi.mock("@/app/manage/actions", () => ({
  addVillager: vi.fn(async () => ({ ok: true })),
  editVillager: vi.fn(async () => ({ ok: true })),
  removeVillager: vi.fn(async () => undefined),
  sendSms: vi.fn(async () => ({ sent: 0 })),
}));

const villagers: Villager[] = [
  { id: 1, name: "Nguyễn Văn A", phone: "0900000001", address: "Bản 1", areaId: "muong_nhe", createdAt: 2 },
  { id: 2, name: "Trần Thị B", phone: "0900000002", address: null, areaId: null, createdAt: 1 },
];

const areaOptions: AreaOption[] = [
  { id: "muong_nhe", name: "Xã Mường Nhé", level: 4, count: 1 },
  { id: "dien_bien_phu", name: "Phường Điện Biên Phủ", level: 2, count: 0 },
];

const smsLogs: SmsLog[] = [
  { id: 1, areaIds: ["muong_nhe"], message: "Cảnh báo lũ quét", recipientCount: 1, createdAt: 3 },
];

describe("VillagerManager", () => {
  it("renders a row per villager", () => {
    render(<VillagerManager villagers={villagers} />);
    expect(screen.getByText("Nguyễn Văn A")).toBeInTheDocument();
    expect(screen.getByText("0900000001")).toBeInTheDocument();
    expect(screen.getByText("Trần Thị B")).toBeInTheDocument();
  });

  it("filters the table by the search keyword", () => {
    render(<VillagerManager villagers={villagers} />);
    fireEvent.change(screen.getByRole("searchbox", { name: "Tìm người dân" }), {
      target: { value: "Trần" },
    });
    expect(screen.queryByText("Nguyễn Văn A")).not.toBeInTheDocument();
    expect(screen.getByText("Trần Thị B")).toBeInTheDocument();
  });

  it("opens the add modal with empty form fields", () => {
    render(<VillagerManager villagers={villagers} />);
    fireEvent.click(screen.getByRole("button", { name: "Thêm người dân" }));
    const dialog = screen.getByRole("dialog", { name: "Thêm người dân" });
    expect(dialog).toBeInTheDocument();
    expect(screen.getByLabelText("Họ tên")).toHaveValue("");
    expect(screen.getByLabelText("Số điện thoại")).toHaveValue("");
  });

  it("prefills the edit modal with the villager's details, including area", () => {
    render(<VillagerManager villagers={villagers} areaOptions={areaOptions} />);
    fireEvent.click(screen.getByRole("button", { name: "Sửa Nguyễn Văn A" }));
    expect(screen.getByRole("dialog", { name: "Sửa thông tin người dân" })).toBeInTheDocument();
    expect(screen.getByLabelText("Họ tên")).toHaveValue("Nguyễn Văn A");
    expect(screen.getByLabelText("Số điện thoại")).toHaveValue("0900000001");
    expect(screen.getByLabelText("Khu vực (không bắt buộc)")).toHaveValue("muong_nhe");
  });

  it("shows sent-SMS history and the sent counter", () => {
    render(<VillagerManager villagers={villagers} areaOptions={areaOptions} smsLogs={smsLogs} />);
    expect(screen.getByText("Đã gửi 1 tin")).toBeInTheDocument();
    expect(screen.getByText("Cảnh báo lũ quét")).toBeInTheDocument();
    // The log targeted "muong_nhe", which resolves to the area name via areaOptions.
    // (It also appears as villager 1's area cell, so there is more than one match.)
    expect(screen.getAllByText("Xã Mường Nhé").length).toBeGreaterThan(0);
  });

  it("narrows the SMS recipient count when a scope is chosen", () => {
    render(<VillagerManager villagers={villagers} areaOptions={areaOptions} smsLogs={smsLogs} />);
    fireEvent.click(screen.getByRole("button", { name: "Gửi SMS khẩn" }));
    // Default scope is "all" — both villagers.
    expect(screen.getByText("2 người dân")).toBeInTheDocument();
    // Switch to "by danger level"; only Mường Nhé (level 4) qualifies → its 1 villager.
    fireEvent.click(screen.getByRole("button", { name: "Theo mức độ" }));
    expect(screen.getByText("1 người dân")).toBeInTheDocument();
  });
});
