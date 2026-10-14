import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DraftProvider, useDrafts } from "./DraftContext";

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ identity: { userId: "user-1", role: "agent" } }),
}));

function Consumer() {
  const { saveDraft, clearDraft } = useDrafts();
  return (
    <>
      <button onClick={() => saveDraft("ticket-1", { body: "unsent", visibility: "Public", files: [] })}>
        save draft
      </button>
      <button onClick={() => clearDraft("ticket-1")}>clear draft</button>
    </>
  );
}

function fireBeforeUnload() {
  const event = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(event);
  return event;
}

describe("draft store warning", () => {
  it("warns while any draft exists and stays quiet when the store is empty", async () => {
    const user = userEvent.setup();
    render(
      <DraftProvider>
        <Consumer />
      </DraftProvider>,
    );

    expect(fireBeforeUnload().defaultPrevented).toBe(false);

    await user.click(screen.getByRole("button", { name: "save draft" }));
    expect(fireBeforeUnload().defaultPrevented).toBe(true);

    await user.click(screen.getByRole("button", { name: "clear draft" }));
    expect(fireBeforeUnload().defaultPrevented).toBe(false);
  });
});
