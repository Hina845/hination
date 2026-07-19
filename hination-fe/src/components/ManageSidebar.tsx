"use client";

import { NavigationArrow } from "@phosphor-icons/react";
import Link from "next/link";

type NavKey = "map" | "dashboard" | "manage" | "radio" | "rescue";

type NavEntry = {
  key: NavKey;
  label: string;
  href?: string; // absent => placeholder route that does not exist yet
};

const NAV_ENTRIES: NavEntry[] = [
  { key: "map", label: "Bản đồ", href: "/app" },
  { key: "manage", label: "Quản lý", href: "/manage" },
  { key: "radio", label: "Đài phát thanh", href: "/radio" },
  { key: "rescue", label: "Cứu hộ", href: "/rescue" },
];

export default function ManageSidebar({ active }: { active: NavKey }) {
  return (
    <aside className="hidden w-64 shrink-0 flex-col gap-9 border-r border-[rgb(15_23_42_/_8%)] bg-white px-6 py-8 text-base md:flex">
      <div className="flex items-center gap-2.5 px-2 text-xl font-bold text-[#0f172a]">
        <NavigationArrow weight="fill" className="size-6 text-[#0f172a]" />
        <span>Điện Biên Forecast</span>
      </div>

      <nav aria-label="Điều hướng" className="flex flex-col gap-1.5">
        {NAV_ENTRIES.map((entry) => {
          const isActive = entry.key === active;
          const className = `rounded-lg px-4 py-2.5 text-base transition-colors ${
            isActive
              ? "bg-[#eef2ff] font-semibold text-[#4f46e5]"
              : "text-[#475569] hover:bg-[#f1f5f9] hover:text-[#0f172a]"
          }`;

          if (!entry.href) {
            return (
              <span
                key={entry.key}
                aria-disabled="true"
                title="Sắp có"
                className="cursor-not-allowed rounded-lg px-4 py-2.5 text-base text-[#cbd5e1]"
              >
                {entry.label}
              </span>
            );
          }

          return (
            <Link
              key={entry.key}
              href={entry.href}
              aria-current={isActive ? "page" : undefined}
              className={className}
            >
              {entry.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
