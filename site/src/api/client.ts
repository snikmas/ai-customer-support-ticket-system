import {
  clearTokens,
  currentSessionGeneration,
  readTokens,
  writeTokens,
} from "../auth/session";
import type { ApiErrorBody, Tokens } from "./types";

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "/api"
).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

let refreshInFlight: Promise<Tokens> | null = null;

// Called by login/logout so a refresh that started under a previous session
// cannot be awaited by a newly signed-in session.
export function resetRefreshState(): void {
  refreshInFlight = null;
}

async function parseError(response: Response): Promise<ApiError> {
  let body: ApiErrorBody = {};
  try {
    body = (await response.json()) as ApiErrorBody;
  } catch {
    // The status remains useful when a proxy returns non-JSON.
  }
  return new ApiError(
    body.error?.message || `Request failed with status ${response.status}`,
    response.status,
    body.error?.code || `http_${response.status}`,
    body.error?.details,
  );
}

async function refreshSession(): Promise<Tokens> {
  if (refreshInFlight) return refreshInFlight;
  const tokens = readTokens();
  if (!tokens) throw new ApiError("Your session has expired", 401, "session_missing");

  const generation = currentSessionGeneration();
  const refreshToken = tokens.refresh_token;

  const pending = fetch(`${API_BASE_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
    .then(async (response) => {
      if (!response.ok) throw await parseError(response);
      const next = (await response.json()) as Tokens;
      if (
        generation !== currentSessionGeneration() ||
        readTokens()?.refresh_token !== refreshToken
      ) {
        // A logout or a later login replaced the session while this refresh
        // was in flight. Never restore the superseded tokens.
        throw new ApiError(
          "Your session changed while it was being refreshed",
          401,
          "session_superseded",
        );
      }
      writeTokens(next);
      window.dispatchEvent(new Event("resolveai:session-refreshed"));
      return next;
    })
    .catch((error) => {
      if (generation === currentSessionGeneration()) {
        clearTokens();
        window.dispatchEvent(new Event("resolveai:session-expired"));
      }
      throw error;
    })
    .finally(() => {
      if (refreshInFlight === pending) refreshInFlight = null;
    });

  refreshInFlight = pending;
  return pending;
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  authenticated?: boolean;
  retryUnauthorized?: boolean;
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const {
    body,
    authenticated = true,
    retryUnauthorized = true,
    headers: providedHeaders,
    ...requestInit
  } = options;

  const headers = new Headers(providedHeaders);
  const isMultipart = typeof FormData !== "undefined" && body instanceof FormData;
  if (body !== undefined && !isMultipart) headers.set("Content-Type", "application/json");
  if (authenticated) {
    const tokens = readTokens();
    if (!tokens) throw new ApiError("Please sign in", 401, "session_missing");
    headers.set("Authorization", `Bearer ${tokens.access_token}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...requestInit,
    headers,
    body: body === undefined ? undefined : isMultipart ? (body as FormData) : JSON.stringify(body),
  });

  if (response.status === 401 && authenticated && retryUnauthorized) {
    await refreshSession();
    return apiRequest<T>(path, { ...options, retryUnauthorized: false });
  }
  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;

  const payload = (await response.json()) as { data?: T } | T;
  if (
    payload !== null &&
    typeof payload === "object" &&
    Object.prototype.hasOwnProperty.call(payload, "data")
  ) {
    return (payload as { data: T }).data;
  }
  return payload as T;
}

export async function downloadFile(path: string, retryUnauthorized = true): Promise<Blob> {
  const tokens = readTokens();
  if (!tokens) throw new ApiError("Please sign in", 401, "session_missing");
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Authorization: `Bearer ${tokens.access_token}` },
  });
  if (response.status === 401 && retryUnauthorized) {
    await refreshSession();
    return downloadFile(path, false);
  }
  if (!response.ok) throw await parseError(response);
  return response.blob();
}

export function toErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof TypeError) {
    return "The API is unavailable. Check that FastAPI is running and the API URL is correct.";
  }
  return "Something unexpected happened.";
}
