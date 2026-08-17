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
    throw new ApiError(response.status, detailOf(body) ?? `Request failed with ${response.status}`);
  }

  return body as T;
}

/**
 * A refused value arrives as a list of field errors rather than a sentence, and a
 * form that answers "request failed with 422" has told the person nothing about the
 * URL they just typed. The validator's own wording is the useful part.
 */
function detailOf(body: unknown): string | null {
  if (!body || typeof body !== "object" || !("detail" in body)) return null;
  const detail = (body as { detail: unknown }).detail;

  if (typeof detail === "string") return detail;
  if (!Array.isArray(detail)) return null;

  const first = detail[0];
  const message = first && typeof first === "object" ? (first as { msg?: unknown }).msg : null;
  return typeof message === "string" ? message.replace(/^Value error, /, "") : null;
}
