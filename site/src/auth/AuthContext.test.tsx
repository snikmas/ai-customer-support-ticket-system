import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, render, waitFor } from "@testing-library/react";
import { AuthProvider, useAuth } from "./AuthContext";
import { clearTokens, writeTokens } from "./session";

function tokens(id: string) {
  return {
    access_token: `x.${btoa(JSON.stringify({ sub: id, role: "user" }))}.x`,
    refresh_token: `synthetic-${id}`,
    token_type: "bearer",
  };
}

function json(data: unknown) {
  return new Response(JSON.stringify(data), {
    headers: { "Content-Type": "application/json" },
  });
}

let auth: ReturnType<typeof useAuth>;
function Observe() {
  auth = useAuth();
  return null;
}

afterEach(() => {
  cleanup();
  clearTokens();
  vi.unstubAllGlobals();
});

// A delayed profile response from a previous session must never replace the
// current session's identity or profile.
it("keeps B's profile after an older A profile response arrives", async () => {
  writeTokens(tokens("A"));
  let resolveA!: (response: Response) => void;
  const pendingA = new Promise<Response>((resolve) => {
    resolveA = resolve;
  });
  const fetchMock = vi.fn((url: string) => {
    if (url.endsWith("/users/A")) return pendingA;
    if (url.endsWith("/auth/logout")) return Promise.resolve(json({}));
    if (url.endsWith("/auth/login")) return Promise.resolve(json(tokens("B")));
    if (url.endsWith("/users/B"))
      return Promise.resolve(json({ data: { id: "B", role: "user" } }));
    throw new Error(`Unexpected URL: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);

  render(
    <AuthProvider>
      <Observe />
    </AuthProvider>,
  );
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  await act(async () => {
    await auth.logout();
  });
  await act(async () => {
    await auth.login("B", "synthetic-password");
  });
  await waitFor(() => expect(auth.user?.id).toBe("B"));

  await act(async () => {
    resolveA(json({ data: { id: "A", role: "user" } }));
  });

  expect(auth.identity?.userId).toBe("B");
  expect(auth.user?.id).toBe("B");
});

// A delayed FAILURE from the previous session must not sign the new user out.
it("does not sign B out when A's stale profile request fails", async () => {
  writeTokens(tokens("A"));
  let rejectA!: (reason: unknown) => void;
  const pendingA = new Promise<Response>((_resolve, reject) => {
    rejectA = reject;
  });
  const fetchMock = vi.fn((url: string) => {
    if (url.endsWith("/users/A")) return pendingA;
    if (url.endsWith("/auth/logout")) return Promise.resolve(json({}));
    if (url.endsWith("/auth/login")) return Promise.resolve(json(tokens("B")));
    if (url.endsWith("/users/B"))
      return Promise.resolve(json({ data: { id: "B", role: "user" } }));
    throw new Error(`Unexpected URL: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);

  render(
    <AuthProvider>
      <Observe />
    </AuthProvider>,
  );
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  await act(async () => {
    await auth.logout();
  });
  await act(async () => {
    await auth.login("B", "synthetic-password");
  });
  await waitFor(() => expect(auth.user?.id).toBe("B"));

  await act(async () => {
    rejectA(new Error("stale request failed"));
  });

  expect(auth.identity?.userId).toBe("B");
  expect(auth.user?.id).toBe("B");
});
