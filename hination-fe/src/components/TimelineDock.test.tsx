import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import TimelineDock from "@/components/TimelineDock";
import type { ForecastDay } from "@/types/forecast";

const days = Array.from({ length: 7 }, (_, index) => ({
  dayOffset: index + 1,
  date: `2026-07-${String(18 + index).padStart(2, "0")}`,
  maximumAlertLevel: ((index % 5) + 1),
  areas: [],
})) as ForecastDay[];

function Harness({ initial = 0 }: { initial?: number }) {
  const [selected, setSelected] = useState(initial);
  return <><output data-testid="selected">{selected}</output><TimelineDock days={days} selected={selected} onSelect={setSelected} /></>;
}

afterEach(() => {
  vi.useRealTimers();
});

describe("forecast playback", () => {
  it("advances exactly once after three seconds and pauses", () => {
    vi.useFakeTimers();
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Phát dự báo" }));
    act(() => vi.advanceTimersByTime(2999));
    expect(screen.getByTestId("selected")).toHaveTextContent("0");
    act(() => vi.advanceTimersByTime(1));
    expect(screen.getByTestId("selected")).toHaveTextContent("1");
    fireEvent.click(screen.getByRole("button", { name: "Tạm dừng" }));
    act(() => vi.advanceTimersByTime(6000));
    expect(screen.getByTestId("selected")).toHaveTextContent("1");
  });

  it("stops on day seven and restarts from day one", () => {
    vi.useFakeTimers();
    render(<Harness initial={5} />);
    fireEvent.click(screen.getByRole("button", { name: "Phát dự báo" }));
    act(() => vi.advanceTimersByTime(3000));
    expect(screen.getByTestId("selected")).toHaveTextContent("6");
    expect(screen.getByRole("button", { name: "Phát dự báo" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Phát dự báo" }));
    expect(screen.getByTestId("selected")).toHaveTextContent("0");
  });

  it("resumes three seconds after a manual selection while playing", () => {
    vi.useFakeTimers();
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Phát dự báo" }));
    act(() => vi.advanceTimersByTime(2000));
    fireEvent.click(screen.getByRole("tab", { name: /22 tháng 07/ }));
    expect(screen.getByTestId("selected")).toHaveTextContent("4");
    act(() => vi.advanceTimersByTime(2999));
    expect(screen.getByTestId("selected")).toHaveTextContent("4");
    act(() => vi.advanceTimersByTime(1));
    expect(screen.getByTestId("selected")).toHaveTextContent("5");
  });
});
