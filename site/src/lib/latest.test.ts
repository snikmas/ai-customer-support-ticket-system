import { describe, expect, it } from "vitest";
import { createLatestGuard } from "./latest";

describe("createLatestGuard", () => {
  it("only treats the most recent generation as current", () => {
    const guard = createLatestGuard();
    const first = guard.begin();
    const second = guard.begin();

    expect(guard.isCurrent(first)).toBe(false);
    expect(guard.isCurrent(second)).toBe(true);
  });

  it("snapshot does not invalidate a sibling request", () => {
    const guard = createLatestGuard();
    const loading = guard.begin();
    const pagination = guard.snapshot();

    expect(pagination).toBe(loading);
    expect(guard.isCurrent(loading)).toBe(true);
  });

  it("invalidate discards every earlier generation", () => {
    const guard = createLatestGuard();
    const ticketA = guard.begin();
    guard.invalidate();

    expect(guard.isCurrent(ticketA)).toBe(false);
  });
});
