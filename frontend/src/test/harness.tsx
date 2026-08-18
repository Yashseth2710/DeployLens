import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";

/**
 * Render a component that reads from the query cache.
 *
 * Retries are off: a component under test that fails a request should report the
 * failure immediately, not sit in a retry loop until the test times out.
 */
export function renderWithQuery(ui: ReactElement): RenderResult {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity },
      mutations: { retry: false },
    },
  });

  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }

  return render(ui, { wrapper: Wrapper });
}

/**
 * Answer `fetch` with whatever each path should return.
 *
 * Keyed by a fragment of the URL so a test names the endpoint it cares about and
 * ignores the rest, which keeps a test from breaking when an unrelated query is
 * added to the same screen.
 */
export function stubFetch(routes: Record<string, unknown>): void {
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    // Longest first, so "/api/alerts/preview" wins over "/api/alerts" rather than
    // whichever happened to be declared earlier.
    const match = Object.keys(routes)
      .sort((a, b) => b.length - a.length)
      .find((path) => url.includes(path));

    if (match === undefined) {
      return new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 });
    }
    return new Response(JSON.stringify(routes[match]), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }) as typeof fetch;
}
