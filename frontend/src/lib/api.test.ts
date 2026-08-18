import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "@/lib/api";

function answer(body: unknown, status = 200): void {
  globalThis.fetch = vi.fn(
    async () =>
      new Response(body === undefined ? null : JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json" },
      }),
  ) as typeof fetch;
}

afterEach(() => vi.restoreAllMocks());

describe("api", () => {
  it("returns the parsed body on success", async () => {
    answer({ username: "octocat" });

    await expect(api<{ username: string }>("/api/auth/me")).resolves.toEqual({
      username: "octocat",
    });
  });

  it("keeps the status on the error so a 401 can be told from an outage", async () => {
    answer({ detail: "Sign in with GitHub to continue" }, 401);

    await expect(api("/api/repositories")).rejects.toMatchObject({
      status: 401,
      message: "Sign in with GitHub to continue",
    });
  });

  it("reports an unreachable API rather than throwing a fetch error", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }) as typeof fetch;

    const error = await api("/api/repositories").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(0);
    expect((error as ApiError).message).toMatch(/could not reach/i);
  });

  it("unwraps a validator's own wording instead of printing the status", async () => {
    // A form that answers "request failed with 422" has told the person nothing
    // about the URL they just typed.
    answer({ detail: [{ msg: "Value error, Give a full http:// or https:// URL" }] }, 422);

    await expect(api("/api/health-checks", { method: "POST", body: "{}" })).rejects.toMatchObject({
      status: 422,
      message: "Give a full http:// or https:// URL",
    });
  });

  it("falls back to the status when the body explains nothing", async () => {
    answer({}, 500);

    await expect(api("/api/analytics/overview")).rejects.toMatchObject({
      status: 500,
      message: "Request failed with 500",
    });
  });

  it("treats an empty response as a result, not a parse failure", async () => {
    globalThis.fetch = vi.fn(async () => new Response(null, { status: 204 })) as typeof fetch;

    await expect(api("/api/health-checks/abc")).resolves.toBeUndefined();
  });
});
