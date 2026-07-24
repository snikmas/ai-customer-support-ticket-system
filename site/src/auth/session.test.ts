import { describe, expect, it } from "vitest";
import { clearTokens, readIdentity, readTokens, writeTokens } from "./session";

function jwt(payload: Record<string, unknown>): string {
  const encode = (value: object) =>
    btoa(JSON.stringify(value)).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
  return `${encode({ alg: "none" })}.${encode(payload)}.signature`;
}

describe("demo session storage", () => {
  it("stores the JSON-token session and reads identity claims", () => {
    const access = jwt({ sub: "user-1", role: "agent" });
    writeTokens({ access_token: access, refresh_token: "refresh", token_type: "bearer" });

    expect(readTokens()?.refresh_token).toBe("refresh");
    expect(readIdentity(access)).toEqual({ userId: "user-1", role: "agent" });

    clearTokens();
    expect(readTokens()).toBeNull();
  });

  it("rejects malformed access-token claims", () => {
    expect(readIdentity("not-a-jwt")).toBeNull();
    expect(readIdentity(jwt({ sub: "user-1" }))).toBeNull();
  });
});
