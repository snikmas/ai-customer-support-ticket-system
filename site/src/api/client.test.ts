import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiRequest } from "./client";
import { readTokens, writeTokens } from "../auth/session";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("apiRequest", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("unwraps the backend data envelope", async () => {
    writeTokens({
      access_token: "access",
      refresh_token: "refresh",
      token_type: "bearer",
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ data: [{ id: "1" }] })));

    await expect(apiRequest<Array<{ id: string }>>("/tickets/")).resolves.toEqual([
      { id: "1" },
    ]);
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/tickets/"),
      expect.objectContaining({
        headers: expect.any(Headers),
      }),
    );
  });

  it("maps the backend error envelope to a safe ApiError", async () => {
    writeTokens({
      access_token: "access",
      refresh_token: "refresh",
      token_type: "bearer",
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          { error: { code: "ticket_forbidden", message: "You cannot view this ticket" } },
          403,
        ),
      ),
    );

    const request = apiRequest("/tickets/hidden");
    await expect(request).rejects.toMatchObject({
      status: 403,
      code: "ticket_forbidden",
      message: "You cannot view this ticket",
    });
  });

  it("rotates tokens once and retries an expired authenticated request", async () => {
    writeTokens({
      access_token: "expired-access",
      refresh_token: "old-refresh",
      token_type: "bearer",
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ error: { message: "expired" } }, 401))
      .mockResolvedValueOnce(
        jsonResponse({
          access_token: "new-access",
          refresh_token: "new-refresh",
          token_type: "bearer",
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ data: { id: "ticket-1" } }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiRequest<{ id: string }>("/tickets/ticket-1")).resolves.toEqual({
      id: "ticket-1",
    });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(readTokens()).toMatchObject({
      access_token: "new-access",
      refresh_token: "new-refresh",
    });
  });
});
