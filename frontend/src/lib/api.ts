export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * Every call carries the session cookie and every failure arrives as an ApiError
 * with its status intact, so a 401 can be told from an outage without parsing
 * a message. The dev server proxies /api to the backend, and Vercel rewrites it
 * in production, so the same relative path works in both.
 */
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      credentials: "same-origin",
      headers: init?.body ? { "Content-Type": "application/json" } : undefined,
      ...init,
    });
  } catch {
    throw new ApiError(0, "Could not reach DeployLens. Is the API running?");
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const body = await response.json().catch(() => null);

  if (!response.ok) {
    const detail =
      body && typeof body === "object" && typeof body.detail === "string"
        ? body.detail
        : `Request failed with ${response.status}`;
    throw new ApiError(response.status, detail);
  }

  return body as T;
}
