import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Reading } from "@/components/reading";

describe("Reading", () => {
  it("prints a measured zero as zero", () => {
    // Zero deploys is a measurement. It must not be dressed up as absence.
    render(<Reading label="Deploys" value={0} sample="30 d" />);

    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.queryByText(/not measured/i)).not.toBeInTheDocument();
  });

  it("says nothing was measured rather than showing a zero", () => {
    // A project with no health check is not a project that is down, and success
    // rate over no decided runs is not 0%. Both are absence, not a value.
    render(<Reading label="Uptime" value={null} />);

    expect(screen.getByText("not measured")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("lets the caller name the absence in the terms of that reading", () => {
    render(<Reading label="Deploys" value={null} absent="no deploy workflow" />);

    expect(screen.getByText("no deploy workflow")).toBeInTheDocument();
  });

  it("keeps the unit beside the number and the sample under it", () => {
    render(<Reading label="Runs passing" value={92.6} unit="%" sample="75 of 81 decided" />);

    expect(screen.getByText("92.6")).toBeInTheDocument();
    expect(screen.getByText("%")).toBeInTheDocument();
    expect(screen.getByText("75 of 81 decided")).toBeInTheDocument();
  });

  it("marks the value for tabular numerals so a column cannot shift width", () => {
    const { container } = render(<Reading label="Runs" value={188} />);

    expect(container.querySelector("[data-numeric]")).toBeInTheDocument();
  });
});
