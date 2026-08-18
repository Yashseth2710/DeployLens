import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AlertBoard } from "@/components/alert-board";
import { renderWithQuery, stubFetch } from "@/test/harness";

const USER = { id: "u1", github_id: 1, username: "octocat", email: null, avatar_url: null };

const STANDING = {
  id: "a1",
  repository_id: "r1",
  kind: "streak",
  subject: "CI",
  detail: "failing 6 runs in a row",
  issue_number: 12,
  issue_url: "https://github.com/octocat/deploylens/issues/12",
  raised_at: new Date().toISOString(),
  resolved_at: null,
};

const RECOVERED = {
  ...STANDING,
  id: "a2",
  subject: "Nightly",
  resolved_at: new Date().toISOString(),
};

afterEach(() => vi.restoreAllMocks());

describe("AlertBoard", () => {
  it("asks a signed-out visitor to sign in rather than showing an empty page", async () => {
    stubFetch({});

    renderWithQuery(<AlertBoard />);

    expect(await screen.findByText(/sign in to see your alerts/i)).toBeInTheDocument();
  });

  it("reports nothing standing when every alert has recovered", async () => {
    stubFetch({ "/api/auth/me": USER, "/api/alerts": [RECOVERED] });

    renderWithQuery(<AlertBoard />);

    expect(await screen.findByText(/nothing standing/i)).toBeInTheDocument();
    // The list loads after the header, so this waits rather than reading the skeleton.
    expect(await screen.findByText(/recovered/i)).toBeInTheDocument();
  });

  it("counts only the alerts still standing", async () => {
    stubFetch({ "/api/auth/me": USER, "/api/alerts": [STANDING, RECOVERED] });

    renderWithQuery(<AlertBoard />);

    expect(await screen.findByText(/1 standing/i)).toBeInTheDocument();
  });

  it("links a filed alert to the issue it opened", async () => {
    stubFetch({ "/api/auth/me": USER, "/api/alerts": [STANDING] });

    renderWithQuery(<AlertBoard />);

    const link = await screen.findByRole("link", { name: /#12/ });
    expect(link).toHaveAttribute("href", STANDING.issue_url);
  });

  it("checks nothing until it is asked to", async () => {
    // The preview reads every connected project. A page that ran it on load would
    // spend that on somebody who only came to read what had already been raised.
    stubFetch({ "/api/auth/me": USER, "/api/alerts": [] });

    renderWithQuery(<AlertBoard />);

    expect(await screen.findByText(/nothing has been checked yet/i)).toBeInTheDocument();
  });

  it("renders the issue it would file, and says it filed nothing", async () => {
    const user = userEvent.setup();
    stubFetch({
      "/api/auth/me": USER,
      "/api/alerts/preview": {
        raised: 1,
        resolved: 0,
        unchanged: 0,
        failed: 0,
        dry_run: true,
        actions: [
          {
            repository: "octocat/deploylens",
            kind: "streak",
            subject: "CI",
            action: "raise",
            title: "CI is failing repeatedly",
            body: "`CI` is failing 6 runs in a row.",
            issue_number: null,
            issue_url: null,
          },
        ],
      },
      "/api/alerts": [],
    });

    renderWithQuery(<AlertBoard />);
    await user.click(await screen.findByRole("button", { name: /check now/i }));

    expect(await screen.findByText("CI is failing repeatedly")).toBeInTheDocument();
    expect(screen.getByText(/would open/i)).toBeInTheDocument();
    // Nothing was filed, so the record below stays empty.
    expect(screen.getByText(/nothing has been raised/i)).toBeInTheDocument();
  });

  it("opens the rendered issue body on request", async () => {
    const user = userEvent.setup();
    stubFetch({
      "/api/auth/me": USER,
      "/api/alerts/preview": {
        raised: 1,
        resolved: 0,
        unchanged: 0,
        failed: 0,
        dry_run: true,
        actions: [
          {
            repository: "octocat/deploylens",
            kind: "streak",
            subject: "CI",
            action: "raise",
            title: "CI is failing repeatedly",
            body: "BODY-MARKER runs read: 6",
            issue_number: null,
            issue_url: null,
          },
        ],
      },
      "/api/alerts": [],
    });

    renderWithQuery(<AlertBoard />);
    await user.click(await screen.findByRole("button", { name: /check now/i }));

    const row = await screen.findByRole("button", { name: /failing repeatedly/i });
    expect(screen.queryByText(/BODY-MARKER/)).not.toBeInTheDocument();

    await user.click(row);
    expect(await screen.findByText(/BODY-MARKER/)).toBeInTheDocument();
  });

  it("says a check found nothing rather than leaving the sheet blank", async () => {
    const user = userEvent.setup();
    stubFetch({
      "/api/auth/me": USER,
      "/api/alerts/preview": {
        raised: 0,
        resolved: 0,
        unchanged: 0,
        failed: 0,
        dry_run: true,
        actions: [],
      },
      "/api/alerts": [],
    });

    renderWithQuery(<AlertBoard />);
    await user.click(await screen.findByRole("button", { name: /check now/i }));

    await waitFor(() => expect(screen.getByText(/nothing worth raising/i)).toBeInTheDocument());
  });
});
