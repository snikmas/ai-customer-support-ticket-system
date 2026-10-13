import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiRequest } from "../api/client";
import type { Comment, Ticket } from "../api/types";
import { ToastProvider } from "../components/ToastContext";
import { TicketDetailPage } from "./TicketDetailPage";

const { managerIdentity, managerUser } = vi.hoisted(() => ({
  managerIdentity: { userId: "manager-1", role: "manager" as const },
  managerUser: {
    id: "manager-1",
    role: "manager" as const,
    first_name: "Man",
    last_name: "Ager",
    nickname: "manager",
    email: "manager@example.com",
    phone: "+1",
    user_status: "Active" as const,
  },
}));

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({
    identity: managerIdentity,
    user: managerUser,
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
  }),
}));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, apiRequest: vi.fn(), downloadFile: vi.fn() };
});

const ticket: Ticket = {
  id: "ticket-1",
  title: "Escalated billing issue",
  description: "Customer cannot process payments.",
  category: "Billing",
  tags: [],
  department_id: "support",
  skill_ids: [],
  assigned_agent_id: null,
  creator_user_id: "customer-1",
  status: "In progress",
  priority: 3,
  updated_at: "2026-01-01T00:00:00Z",
  created_at: "2026-01-01T00:00:00Z",
  due_at: null,
  is_overdue: false,
  deleted_at: null,
};

function newestFirstPage(): Comment[] {
  return Array.from({ length: 50 }, (_, index) => ({
    id: `comment-${50 - index}`,
    ticket_id: "ticket-1",
    author_user_id: "customer-1",
    body:
      index === 0
        ? "Newest reply beyond the first hundred"
        : `Historical comment ${50 - index}`,
    visibility: "Public",
    edited_at: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    deleted_at: null,
    deleted_by_user_id: null,
    parent_comment_id: null,
    attachments_count: 0,
    source: "Web",
  }));
}

function renderPage() {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={["/tickets/ticket-1"]}>
        <Routes>
          <Route path="/tickets/:ticketId" element={<TicketDetailPage />} />
        </Routes>
      </MemoryRouter>
    </ToastProvider>,
  );
}

const apiMock = vi.mocked(apiRequest);

describe("TicketDetailPage conversation and error states", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === "/tickets/ticket-1") {
        if (options?.method === "PATCH") {
          throw new ApiError("The ticket changed", 409, "ticket_status_conflict");
        }
        return ticket;
      }
      if (path.startsWith("/tickets/ticket-1/comments?")) {
        return path.includes("offset=") ? [] : newestFirstPage();
      }
      if (path.startsWith("/tickets/ticket-1/comments/")) {
        return [];
      }
      if (path.startsWith("/tickets/ticket-1/history")) {
        return [];
      }
      if (path === "/departments/" || path === "/skills/") {
        return [];
      }
      if (path.startsWith("/tickets/ticket-1/analysis-results")) {
        return [];
      }
      if (path.startsWith("/users/assignment-candidates")) {
        return [];
      }
      if (path.startsWith("/users/")) {
        return [];
      }
      return {};
    });
  });

  it("shows the newest reply and an earlier-comments control when over one page exists", async () => {
    renderPage();

    expect(
      await screen.findByText("Newest reply beyond the first hundred"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /load earlier comments/i })).toBeInTheDocument();
    expect(
      apiMock.mock.calls.some(([path]) =>
        String(path).includes("comments?limit=50&sort_order=desc"),
      ),
    ).toBe(true);
  });

  it("surfaces a 409 conflict with a reload path instead of overwriting state", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Escalated billing issue");
    await user.click(await screen.findByRole("button", { name: "Move to Pending" }));

    await waitFor(() =>
      expect(screen.getByText(/reload it before retrying/i)).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /reload ticket/i })).toBeInTheDocument();
  });
});
