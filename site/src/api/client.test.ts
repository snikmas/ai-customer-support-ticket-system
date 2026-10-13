import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiRequest } from "./client";
import { bumpSessionGeneration, clearTokens, readTokens, writeTokens } from "../auth/session";

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


describe("downloadFile", () => {
  it("refreshes an expired session before retrying a download", async () => {
    const { downloadFile } = await import("./client");
    writeTokens({ access_token: "expired", refresh_token: "synthetic-refresh", token_type: "bearer" });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({}, 401))
      .mockResolvedValueOnce(jsonResponse({ access_token: "fresh", refresh_token: "next", token_type: "bearer" }))
      .mockResolvedValueOnce(new Response("synthetic file"));
    vi.stubGlobal("fetch", fetchMock);
    expect((await downloadFile("/attachments/test")).size).toBe(14);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});


describe("session lifecycle races", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("does not restore tokens when the session is cleared while a refresh is in flight", async () => {
    writeTokens({ access_token: "expired", refresh_token: "old-refresh", token_type: "bearer" });
    let resolveRefresh: (response: Response) => void = () => {};
    const refreshGate = new Promise<Response>((resolve) => {
      resolveRefresh = resolve;
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ error: { message: "expired" } }, 401))
      .mockImplementationOnce(() => refreshGate);
    vi.stubGlobal("fetch", fetchMock);

    const pending = apiRequest("/tickets/ticket-1");
    // Let the first 401 resolve and the refresh request start.
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fetchMock).toHaveBeenCalledTimes(2);

    // Simulate a logout racing the refresh.
    clearTokens();
    bumpSessionGeneration();
    resolveRefresh(
      jsonResponse({
        access_token: "resurrected",
        refresh_token: "resurrected-refresh",
        token_type: "bearer",
      }),
    );

    await expect(pending).rejects.toBeInstanceOf(ApiError);
    expect(readTokens()).toBeNull();
  });

  it("maps a 409 business conflict to a typed ApiError", async () => {
    writeTokens({ access_token: "access", refresh_token: "refresh", token_type: "bearer" });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          { error: { code: "ticket_status_conflict", message: "The ticket changed" } },
          409,
        ),
      ),
    );

    await expect(apiRequest("/tickets/ticket-1")).rejects.toMatchObject({
      status: 409,
      code: "ticket_status_conflict",
    });
  });
});
