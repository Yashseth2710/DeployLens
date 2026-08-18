import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ExpandingList } from "@/components/expanding-list";

function rows(count: number): string[] {
  return Array.from({ length: count }, (_, index) => `row ${index + 1}`);
}

function renderList(items: string[], props: Record<string, unknown> = {}) {
  return render(
    <ExpandingList items={items} collapsedLength={5} noun="rows" {...props}>
      {(item: string) => <li key={item}>{item}</li>}
    </ExpandingList>,
  );
}

describe("ExpandingList", () => {
  it("shows only the collapsed length and counts what is hidden", () => {
    renderList(rows(9));

    expect(screen.getAllByRole("listitem")).toHaveLength(5);
    expect(screen.getByRole("button", { name: /4 more rows/i })).toBeInTheDocument();
  });

  it("offers no control when everything already fits", () => {
    renderList(rows(3));

    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("opens to the full list and closes again", async () => {
    const user = userEvent.setup();
    renderList(rows(9));

    await user.click(screen.getByRole("button", { name: /4 more rows/i }));
    expect(screen.getAllByRole("listitem")).toHaveLength(9);

    await user.click(screen.getByRole("button", { name: /show fewer/i }));
    expect(screen.getAllByRole("listitem")).toHaveLength(5);
  });

  it("reports its state to assistive technology", async () => {
    const user = userEvent.setup();
    renderList(rows(9));

    const control = screen.getByRole("button");
    expect(control).toHaveAttribute("aria-expanded", "false");
    await user.click(control);
    expect(screen.getByRole("button")).toHaveAttribute("aria-expanded", "true");
  });

  it("does not offer to show fewer rows than are on screen", () => {
    // Expanding, then filtering to a list that already fits, once left the control
    // reading "show fewer" above rows that were all visible. Expansion is derived
    // from whether anything is actually hidden, so the state cannot survive that.
    const { rerender } = renderList(rows(9));

    rerender(
      <ExpandingList items={rows(2)} collapsedLength={5} noun="rows">
        {(item: string) => <li key={item}>{item}</li>}
      </ExpandingList>,
    );

    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("tells its parent when it opens, so a layout can answer to it", async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    renderList(rows(9), { onToggle });

    await user.click(screen.getByRole("button"));
    expect(onToggle).toHaveBeenCalledWith(true);

    await user.click(screen.getByRole("button"));
    expect(onToggle).toHaveBeenLastCalledWith(false);
  });

  it("announces changing rows only when asked to", () => {
    const { container, rerender } = renderList(rows(9));
    expect(container.querySelector("ul")).not.toHaveAttribute("aria-live");

    rerender(
      <ExpandingList items={rows(9)} collapsedLength={5} noun="rows" live>
        {(item: string) => <li key={item}>{item}</li>}
      </ExpandingList>,
    );
    expect(container.querySelector("ul")).toHaveAttribute("aria-live", "polite");
  });
});
