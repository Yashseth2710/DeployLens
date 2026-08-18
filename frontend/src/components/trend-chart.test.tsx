import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TrendChart, type Plot } from "@/components/trend-chart";

function plot(day: string, total: number, failed = 0): Plot {
  return { day, total, failed, detail: `${total} runs` };
}

function columns(container: HTMLElement): HTMLElement[] {
  const plotted = container.querySelector('[role="img"]');
  return Array.from(plotted?.children ?? []) as HTMLElement[];
}

describe("TrendChart", () => {
  it("says so plainly rather than drawing an empty plot", () => {
    render(<TrendChart points={[]} windowDays={30} unit="runs" emptyLabel="No run recorded." />);

    expect(screen.getByText("No run recorded.")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("puts the quiet days back between two marks", () => {
    // The API returns only days that recorded something. Four deploys spread over a
    // week must not render as four adjacent columns, which would read as four
    // consecutive days of shipping.
    const { container } = render(
      <TrendChart
        points={[plot("2026-08-10", 3), plot("2026-08-14", 5)]}
        windowDays={30}
        unit="deploys"
        emptyLabel="none"
      />,
    );

    expect(columns(container)).toHaveLength(5);
  });

  it("never draws more days than the window asked for", () => {
    const { container } = render(
      <TrendChart
        points={[plot("2026-08-01", 1), plot("2026-08-18", 1)]}
        windowDays={7}
        unit="runs"
        emptyLabel="none"
      />,
    );

    expect(columns(container)).toHaveLength(7);
  });

  it("prints one date when the series is a single day", () => {
    // The same date at both ends of a narrow row sets the label over itself, which
    // rendered as "AUG 17 AUG 17" overlapping.
    render(
      <TrendChart points={[plot("2026-08-17", 4)]} windowDays={30} unit="runs" emptyLabel="none" />,
    );

    // The sr-only summary names the day too, so only the axis row is counted.
    const axis = document.querySelector(".label.flex.justify-between");
    expect(axis?.children).toHaveLength(1);
  });

  it("carries the whole series in text for a reader who cannot see it", () => {
    render(
      <TrendChart
        points={[plot("2026-08-10", 3), plot("2026-08-11", 9)]}
        windowDays={30}
        unit="runs"
        emptyLabel="none"
      />,
    );

    const described = screen.getByRole("img").getAttribute("aria-labelledby");
    expect(described).toBeTruthy();
    const summary = document.getElementById(described!);
    expect(summary?.textContent).toContain("2 days with activity");
    expect(summary?.textContent).toContain("Peak 9 runs");
  });

  it("reports the peak against the busiest day, not the newest", () => {
    render(
      <TrendChart
        points={[plot("2026-08-10", 40), plot("2026-08-11", 2)]}
        windowDays={30}
        unit="runs"
        emptyLabel="none"
      />,
    );

    expect(screen.getAllByText(/peak 40 runs/i).length).toBeGreaterThan(0);
  });

  it("draws a day with nothing recorded as a baseline rule, not a column", () => {
    const { container } = render(
      <TrendChart
        points={[plot("2026-08-10", 6), plot("2026-08-12", 6)]}
        windowDays={30}
        unit="runs"
        emptyLabel="none"
      />,
    );

    const [, gap] = columns(container);
    expect(gap.getAttribute("title")).toContain("nothing recorded");
    expect(gap.style.height).toBe("1px");
  });
});
