import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ReliabilityTrends } from "@/components/reliability-trends";
import type { Trends } from "@/lib/types";

const TRENDS: Trends = {
  window_days: 30,
  runs: [
    { day: "2026-08-10", runs: 12, succeeded: 10, failed: 2, average_duration_seconds: 61 },
    { day: "2026-08-11", runs: 30, succeeded: 30, failed: 0, average_duration_seconds: 58 },
  ],
  deployments: [
    { day: "2026-08-10", deployments: 1, succeeded: 1, failed: 0, average_duration_seconds: null },
  ],
  uptime: [],
};

const EMPTY: Trends = { window_days: 30, runs: [], deployments: [], uptime: [] };

describe("ReliabilityTrends", () => {
  it("counts the days on screen, not the days it holds altogether", async () => {
    // The meta once counted the union of all three series, so it read "3 days
    // plotted" over a deploys chart showing one — describing something else.
    const user = userEvent.setup();
    render(<ReliabilityTrends trends={TRENDS} loading={false} windowDays={30} />);

    expect(screen.getByText(/2 days plotted/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "deploys" }));
    expect(screen.getByText(/1 day plotted/i)).toBeInTheDocument();
  });

  it("says which series is on screen", async () => {
    const user = userEvent.setup();
    render(<ReliabilityTrends trends={TRENDS} loading={false} windowDays={30} />);

    const control = screen.getByRole("group", { name: /series/i });
    expect(control).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "uptime" }));
    expect(screen.getByRole("button", { name: "uptime" })).toHaveAttribute("aria-pressed", "true");
  });

  it("explains an empty series in the terms of that series", async () => {
    const user = userEvent.setup();
    render(<ReliabilityTrends trends={TRENDS} loading={false} windowDays={30} />);

    await user.click(screen.getByRole("button", { name: "uptime" }));
    expect(screen.getByText(/no endpoint read in this window/i)).toBeInTheDocument();
  });

  it("offers the first-run explanation only when nothing at all was collected", () => {
    render(<ReliabilityTrends trends={EMPTY} loading={false} windowDays={30} />);

    expect(screen.getByText(/nothing plotted yet/i)).toBeInTheDocument();
  });

  it("says it is reading rather than showing an empty chart", () => {
    render(<ReliabilityTrends trends={undefined} loading windowDays={30} />);

    expect(screen.getByText("How it got here")).toBeInTheDocument();
    expect(document.querySelector("[aria-busy='true']")).toBeInTheDocument();
  });
});
