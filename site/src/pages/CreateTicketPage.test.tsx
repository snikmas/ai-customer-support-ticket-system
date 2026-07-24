import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../api/client";
import type { Ticket } from "../api/types";
import { CreateTicketPage } from "./CreateTicketPage";

vi.mock("../api/client", () => ({
  apiRequest: vi.fn(),
  toErrorMessage: (error: unknown) =>
    error instanceof Error ? error.message : "Unexpected error",
}));

const createdTicket: Ticket = {
  id: "ticket-1",
  title: "Unicode problem",
  description: "I cannot see clearly",
  category: "API_Error",
  tags: ["timeout"],
  department_id: null,
  skill_ids: [],
  assigned_agent_id: null,
  creator_user_id: "customer-1",
  status: "New",
  priority: 2,
  updated_at: "2026-07-24T03:00:00Z",
  created_at: "2026-07-24T03:00:00Z",
  due_at: "2026-07-24T05:00:00Z",
  is_overdue: false,
  deleted_at: null,
};

describe("customer ticket creation", () => {
  beforeEach(() => {
    vi.mocked(apiRequest).mockReset();
    vi.mocked(apiRequest).mockResolvedValue(createdTicket);
  });

  it("submits customer-visible fields without internal routing metadata", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <CreateTicketPage />
      </MemoryRouter>,
    );

    expect(screen.queryByLabelText(/department/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Required skills")).not.toBeInTheDocument();

    await user.type(screen.getByLabelText(/title/i), "Unicode problem");
    await user.type(screen.getByLabelText(/description/i), "I cannot see clearly");
    await user.click(screen.getByLabelText("timeout"));
    await user.click(screen.getByRole("button", { name: "Create ticket" }));

    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith("/tickets/", {
        method: "POST",
        body: {
          title: "Unicode problem",
          description: "I cannot see clearly",
          category: "API_Error",
          tags: ["timeout"],
        },
      }),
    );
  });
});
