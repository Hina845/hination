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

describe("week slider", () => {
  function renderSlider(overrides: Record<string, unknown> = {}) {
    const onSelectIndex = vi.fn();
    const onSelect = vi.fn();
    render(
      <TimelineDock
        days={days}
        selected={0}
        onSelect={onSelect}
        slotsPerDay={6}
        selectedIndex={1}
        onSelectIndex={onSelectIndex}
        selectedFraction={8 / 168}
        selectedLabel="CN 18 - 08:00"
        nowIndex={7}
        nowFraction={31 / 168}
        {...overrides}
      />,
    );
    return { onSelectIndex, onSelect };
  }

  it("renders a draggable slider with the floating time tooltip", () => {
    renderSlider();
    const slider = screen.getByRole("slider", { name: "Chọn thời điểm dự báo" });
    expect(slider).toHaveAttribute("aria-valuenow", "1");
    expect(slider).toHaveAttribute("aria-valuemax", "41"); // 7 days × 6 slots − 1
    expect(screen.getByText("CN 18 - 08:00")).toBeInTheDocument();
  });

  it("nudges by one 4-hour slot with arrow keys, clamped to the ends", () => {
    const { onSelectIndex } = renderSlider({ selectedIndex: 5 });
    const slider = screen.getByRole("slider", { name: "Chọn thời điểm dự báo" });
    fireEvent.keyDown(slider, { key: "ArrowRight" });
    expect(onSelectIndex).toHaveBeenLastCalledWith(6);
    fireEvent.keyDown(slider, { key: "ArrowLeft" });
    expect(onSelectIndex).toHaveBeenLastCalledWith(4);
    fireEvent.keyDown(slider, { key: "End" });
    expect(onSelectIndex).toHaveBeenLastCalledWith(41);
  });

  it("jumps to now via the now marker", () => {
    const { onSelectIndex } = renderSlider();
    fireEvent.click(screen.getByRole("button", { name: "Về thời điểm hiện tại" }));
    expect(onSelectIndex).toHaveBeenCalledWith(7);
  });

  it("selects a day from the day bar", () => {
    const { onSelect } = renderSlider({ nowFraction: null, nowIndex: -1 });
    fireEvent.click(screen.getByRole("button", { name: /20 tháng 07/ }));
    expect(onSelect).toHaveBeenCalledWith(2);
  });

  it("falls back to plain day tabs when slider props are absent", () => {
    render(<TimelineDock days={days} selected={0} onSelect={() => {}} />);
    expect(screen.queryByRole("slider")).not.toBeInTheDocument();
    expect(screen.getAllByRole("tab")).toHaveLength(7);
  });
});

describe("selected-forecast labels", () => {
  it("labels each day with the selected forecast's level instead of the global maximum", () => {
    const dayLevels = [1, 5, 3, 2, 4, 1, 2];
    render(<TimelineDock days={days} dayLevels={dayLevels} selected={0} onSelect={() => {}} />);
    // Day 19 July → level 5, flagged dangerous by the timeline.
    expect(screen.getByRole("tab", { name: /19 tháng 07, cảnh báo cấp 5 \(nguy hiểm\)/ })).toBeInTheDocument();
    // Day 18 July → level 1, not dangerous, even though the day object's maximumAlertLevel is 1.
    expect(screen.getByRole("tab", { name: /18 tháng 07, cảnh báo cấp 1$/ })).toBeInTheDocument();
  });
});
