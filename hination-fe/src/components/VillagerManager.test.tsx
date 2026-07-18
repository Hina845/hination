import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import VillagerManager from "@/components/VillagerManager";
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
  { id: 1, name: "Nguyễn Văn A", phone: "0900000001", address: "Bản 1", createdAt: 2 },
  { id: 2, name: "Trần Thị B", phone: "0900000002", address: null, createdAt: 1 },
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

  it("prefills the edit modal with the villager's details", () => {
    render(<VillagerManager villagers={villagers} />);
    fireEvent.click(screen.getByRole("button", { name: "Sửa Nguyễn Văn A" }));
    expect(screen.getByRole("dialog", { name: "Sửa thông tin người dân" })).toBeInTheDocument();
    expect(screen.getByLabelText("Họ tên")).toHaveValue("Nguyễn Văn A");
    expect(screen.getByLabelText("Số điện thoại")).toHaveValue("0900000001");
  });
});
