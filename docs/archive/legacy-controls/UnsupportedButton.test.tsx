import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ToastProvider } from "./ToastContext";
import { UnsupportedButton } from "./UnsupportedButton";

describe("unsupported design controls", () => {
  it("explain that the feature is not supported instead of faking behavior", async () => {
    render(
      <ToastProvider>
        <UnsupportedButton feature="Notifications">Notifications</UnsupportedButton>
      </ToastProvider>,
    );

    await userEvent.click(screen.getByRole("button", { name: "Notifications" }));
    expect(screen.getByRole("status")).toHaveTextContent("Notifications is not supported yet.");
  });
});
