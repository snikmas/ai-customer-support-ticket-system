import type { SessionIdentity, Tokens } from "../api/types";

const SESSION_KEY = "resolveai.demo.session";

export function readTokens(): Tokens | null {
  const raw = sessionStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<Tokens>;
    if (!value.access_token || !value.refresh_token) return null;
    return {
      access_token: value.access_token,
      refresh_token: value.refresh_token,
      token_type: value.token_type ?? "bearer",
    };
  } catch {
    sessionStorage.removeItem(SESSION_KEY);
    return null;
  }
}

export function writeTokens(tokens: Tokens): void {
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(tokens));
}

export function clearTokens(): void {
  sessionStorage.removeItem(SESSION_KEY);
}

function decodePart(value: string): Record<string, unknown> | null {
  try {
    const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
    const padding = "=".repeat((4 - (normalized.length % 4)) % 4);
    return JSON.parse(atob(normalized + padding)) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export function readIdentity(accessToken: string): SessionIdentity | null {
  const payload = decodePart(accessToken.split(".")[1] ?? "");
  if (typeof payload?.sub !== "string" || typeof payload?.role !== "string") {
    return null;
  }
  return {
    userId: payload.sub,
    role: payload.role as SessionIdentity["role"],
  };
}
