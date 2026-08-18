import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { formatDuration, formatHours, formatWhen, outcomeOf, runOutcome } from "@/lib/outcome";

describe("outcomeOf", () => {
  it("reads the three decided verdicts GitHub actually sends", () => {
    expect(outcomeOf("success")).toBe("ok");
    expect(outcomeOf("failure")).toBe("hold");
    expect(outcomeOf("timed_out")).toBe("hold");
    expect(outcomeOf("startup_failure")).toBe("hold");
  });

  it("treats anything still moving as waiting rather than decided", () => {
    for (const status of ["queued", "in_progress", "requested", "waiting", "pending"]) {
      expect(outcomeOf(status)).toBe("wait");
    }
  });

  it("does not count an unrecognised conclusion as a failure", () => {
    // GitHub keeps adding conclusions. Guessing "hold" would report a red build
    // for something that may have been fine.
    expect(outcomeOf("neutral")).toBe("none");
    expect(outcomeOf("skipped")).toBe("none");
    expect(outcomeOf("something_new_github_added")).toBe("none");
  });
});

describe("runOutcome", () => {
  it("falls back to status while a run has no conclusion yet", () => {
    expect(runOutcome("in_progress", null)).toBe("wait");
  });

  it("prefers the conclusion once the run is decided", () => {
    expect(runOutcome("completed", "failure")).toBe("hold");
    expect(runOutcome("completed", "success")).toBe("ok");
  });
});

describe("formatDuration", () => {
  it("keeps not-measured distinct from zero", () => {
    // A provider deploy records no duration. Printing "0s" would claim a build
    // that took no time, which is a different statement from "not timed".
    expect(formatDuration(null)).toBeNull();
    expect(formatDuration(0)).toBe("0s");
  });

  it("pads the seconds so a column of times stays aligned", () => {
    expect(formatDuration(65)).toBe("1:05");
    expect(formatDuration(600)).toBe("10:00");
  });

  it("drops the minute entirely under a minute", () => {
    expect(formatDuration(7)).toBe("7s");
    expect(formatDuration(59)).toBe("59s");
  });
});

describe("formatHours", () => {
  it("keeps nothing-merged distinct from merged instantly", () => {
    expect(formatHours(null)).toBeNull();
    expect(formatHours(0)).toBe("0m");
  });

  it("says minutes under an hour and days past two", () => {
    expect(formatHours(0.5)).toBe("30m");
    expect(formatHours(5.25)).toBe("5.3h");
    expect(formatHours(30)).toBe("30h");
    expect(formatHours(72)).toBe("3d");
  });
});

describe("formatWhen", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-18T12:00:00Z"));
  });
  afterEach(() => vi.useRealTimers());

  it("says never rather than inventing a date", () => {
    expect(formatWhen(null)).toBe("never");
  });

  it("climbs through the units as the gap widens", () => {
    expect(formatWhen("2026-08-18T11:59:40Z")).toBe("just now");
    expect(formatWhen("2026-08-18T11:45:00Z")).toBe("15m ago");
    expect(formatWhen("2026-08-18T09:00:00Z")).toBe("3h ago");
    expect(formatWhen("2026-08-17T12:00:00Z")).toBe("yesterday");
    expect(formatWhen("2026-08-14T12:00:00Z")).toBe("4d ago");
  });
});
