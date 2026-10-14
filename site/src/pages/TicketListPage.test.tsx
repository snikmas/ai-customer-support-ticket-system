import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../api/client";
import type { Ticket } from "../api/types";
import { TicketListPage } from "./TicketListPage";

const { agentIdentity, agentUser } = vi.hoisted(() => ({
  agentIdentity: { userId: "agent-1", role: "agent" as const },
  agentUser: {
    id: "agent-1",
    role: "agent" as const,
    first_name: "Agent",
    last_name: "One",
    nickname: "agent",
    email: "agent@example.com",
    phone: "+1",
    user_status: "Active" as const,
  },
}));

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({
    identity: agentIdentity,
    user: agentUser,
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
  }),
}));

vi.mock("../api/client", () => ({
  apiRequest: vi.fn(),
  toErrorMessage: (error: unknown) =>
    error instanceof Error ? error.message : "Unexpected error",
}));

function makeTicket(index: number): Ticket {
  return {
    id: `ticket-${index}`,
    title: `Ticket ${index}`,
    description: "desc",
    category: "API_Error",
    tags: [],
    department_id: null,
    skill_ids: [],
    assigned_agent_id: null,
    assigned_agent_name: null,
    creator_user_id: "customer-1",
    status: "New",
    priority: 2,
    updated_at: "2026-01-01T00:00:00Z",
    created_at: "2026-01-01T00:00:00Z",
    due_at: null,
    is_overdue: false,
    deleted_at: null,
  };
}

const apiMock = vi.mocked(apiRequest);

function mockPages(total: number) {
  apiMock.mockImplementation(async (...args: unknown[]) => {
    const path = String(args[0]);
    if (path.startsWith("/tickets/?")) {
      const url = new URL(path, "http://test");
      const offset = Number(url.searchParams.get("offset") || "0");
      const limit = Number(url.searchParams.get("limit") || "20");
      return Array.from({ length: Math.max(0, Math.min(limit, total - offset)) }, (_, i) =>
        makeTicket(offset + i + 1),
      );
    }
    if (path === "/departments/") return [];
    return {};
  });
}

function renderAt(entry: string) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <TicketListPage />
    </MemoryRouter>,
  );
}

describe("ticket list pagination", () => {
  beforeEach(() => {
    apiMock.mockReset();
  });

  it("disables Next on the last page for exactly 40 tickets", async () => {
    mockPages(40);
    const user = userEvent.setup();
    renderAt("/tickets");

    expect(await screen.findByText("Page 1 · 20 results")).toBeInTheDocument();
    const next = screen.getByRole("button", { name: "Next page" });
    expect(next).toBeEnabled();

    await user.click(next);

    expect(await screen.findByText("Page 2 · 20 results")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Previous page" })).toBeEnabled();
  });

  it("keeps the list reachable for 41 tickets on the final partial page", async () => {
    mockPages(41);
    const user = userEvent.setup();
    renderAt("/tickets?page=3");

    expect(await screen.findByText("Page 3 · 1 result")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Previous page" })).toBeEnabled();
  });

  it("shows an empty-page message with a Previous control on a later empty page", async () => {
    mockPages(0);
    renderAt("/tickets?page=2");

    expect(await screen.findByText("No tickets on this page")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous page" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
  });

  it("treats an empty first page as no results", async () => {
    mockPages(0);
    renderAt("/tickets");

    await waitFor(() => expect(screen.getByText("No tickets found")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Previous page" })).not.toBeInTheDocument();
  });
});
