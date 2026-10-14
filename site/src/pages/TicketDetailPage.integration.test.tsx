import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiRequest } from "../api/client";
import type { AnalysisResult, Comment, Ticket } from "../api/types";
import { DraftProvider } from "../components/DraftContext";
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
  assigned_agent_name: null,
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
    author_display_name: null,
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
      <DraftProvider>
        <MemoryRouter initialEntries={["/tickets/ticket-1"]}>
          <Routes>
            <Route path="/tickets/:ticketId" element={<TicketDetailPage />} />
          </Routes>
        </MemoryRouter>
      </DraftProvider>
    </ToastProvider>,
  );
}

const apiMock = vi.mocked(apiRequest);

function DraftHarness() {
  const [nonce, setNonce] = useState(0);
  return (
    <>
      <button onClick={() => setNonce((value) => value + 1)}>remount ticket</button>
      <TicketDetailPage key={nonce} />
    </>
  );
}

function renderHarness() {
  return render(
    <ToastProvider>
      <DraftProvider>
        <MemoryRouter initialEntries={["/tickets/ticket-1"]}>
          <Routes>
            <Route path="/tickets/:ticketId" element={<DraftHarness />} />
          </Routes>
        </MemoryRouter>
      </DraftProvider>
    </ToastProvider>,
  );
}

function draftMock(post: (path: string) => unknown) {
  apiMock.mockImplementation(async (path: string, options?: { method?: string }) => {
    if (path === "/tickets/ticket-1") return ticket;
    if (path === "/tickets/ticket-1/comments") {
      if (options?.method === "POST") return post(path);
      return [];
    }
    if (path.startsWith("/tickets/ticket-1/comments?") || path.startsWith("/tickets/ticket-1/history")) return [];
    if (path === "/departments/" || path === "/skills/") return [];
    if (path.startsWith("/tickets/ticket-1/analysis-results")) return [];
    if (path.startsWith("/users/")) return [];
    return {};
  });
}

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

  it("reports analysis as queued first, then completed only after the result arrives", async () => {
    const pending: AnalysisResult = {
      id: "analysis-1",
      summary: null,
      error_code: null,
      error_message: null,
      ticket_id: "ticket-1",
      job_id: "job-1",
      provider: "fake",
      model: "deterministic",
      prompt_version: "stage0",
      input_tokens: null,
      output_tokens: null,
      requester_id: "manager-1",
      attempt_count: 1,
      created_at: "2026-01-01T00:00:00Z",
      started_at: null,
      completed_at: null,
      updated_at: "2026-01-01T00:00:00Z",
      status: "pending",
    };
    const completed: AnalysisResult = {
      ...pending,
      status: "completed",
      summary: "Synthetic summary",
      completed_at: "2026-01-01T00:01:00Z",
    };

    apiMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === "/tickets/ticket-1") return ticket;
      if (path.startsWith("/tickets/ticket-1/comments?")) return [];
      if (path.startsWith("/tickets/ticket-1/history")) return [];
      if (path === "/departments/" || path === "/skills/") return [];
      if (path === "/tickets/ticket-1/analysis-results?limit=20") return [];
      if (path === "/tickets/ticket-1/analysis-results" && options?.method === "POST") return pending;
      if (path === "/analysis-results/analysis-1") return completed;
      if (path.startsWith("/users/assignment-candidates")) return [];
      if (path.startsWith("/users/")) return [];
      return {};
    });

    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Escalated billing issue");
    await user.click(screen.getByRole("button", { name: "Run analysis" }));

    expect(await screen.findByText("Analysis queued.")).toBeInTheDocument();
    expect(await screen.findByText("Analysis completed.", {}, { timeout: 4000 })).toBeInTheDocument();
  });

  it("never announces analysis completion for a failed attempt", async () => {
    const pending: AnalysisResult = {
      id: "analysis-2",
      summary: null,
      error_code: null,
      error_message: null,
      ticket_id: "ticket-1",
      job_id: "job-2",
      provider: "fake",
      model: "deterministic",
      prompt_version: "stage0",
      input_tokens: null,
      output_tokens: null,
      requester_id: "manager-1",
      attempt_count: 1,
      created_at: "2026-01-01T00:00:00Z",
      started_at: null,
      completed_at: null,
      updated_at: "2026-01-01T00:00:00Z",
      status: "pending",
    };
    const failed: AnalysisResult = {
      ...pending,
      status: "failed",
      error_code: "worker_unavailable",
      error_message: "The analysis worker is unavailable.",
    };

    apiMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === "/tickets/ticket-1") return ticket;
      if (path.startsWith("/tickets/ticket-1/comments?")) return [];
      if (path.startsWith("/tickets/ticket-1/history")) return [];
      if (path === "/departments/" || path === "/skills/") return [];
      if (path === "/tickets/ticket-1/analysis-results?limit=20") return [];
      if (path === "/tickets/ticket-1/analysis-results" && options?.method === "POST") return pending;
      if (path === "/analysis-results/analysis-2") return failed;
      if (path.startsWith("/users/assignment-candidates")) return [];
      if (path.startsWith("/users/")) return [];
      return {};
    });

    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Escalated billing issue");
    await user.click(screen.getByRole("button", { name: "Run analysis" }));

    expect(await screen.findByText("Analysis queued.")).toBeInTheDocument();
    expect(await screen.findByText("Analysis failed. Review the error and retry.", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.queryByText("Analysis completed.")).not.toBeInTheDocument();
  });

  it("clears the draft after a successful reply through the real parent refresh", async () => {
    draftMock(() => ({ id: "comment-new" }));
    const user = userEvent.setup();
    renderHarness();

    await screen.findByText("Escalated billing issue");
    const composer = screen.getByPlaceholderText("Write a reply…");
    await user.type(composer, "A reply that must not duplicate");
    expect(await screen.findByText("Unsent draft saved for this ticket.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Submit reply" }));
    await screen.findByText("Reply posted.");

    expect((screen.getByPlaceholderText("Write a reply…") as HTMLTextAreaElement).value).toBe("");
    expect(screen.queryByText("Unsent draft saved for this ticket.")).not.toBeInTheDocument();

    // Remounting the ticket must not restore committed text as an unsent draft.
    await user.click(screen.getByRole("button", { name: "remount ticket" }));
    await screen.findByText("Escalated billing issue");
    expect((screen.getByPlaceholderText("Write a reply…") as HTMLTextAreaElement).value).toBe("");
  });

  it("preserves the draft when the reply request fails", async () => {
    draftMock(() => {
      throw new ApiError("Server error", 500, "internal_server_error");
    });
    const user = userEvent.setup();
    renderHarness();

    await screen.findByText("Escalated billing issue");
    await user.type(screen.getByPlaceholderText("Write a reply…"), "Keep me on failure");
    await user.click(screen.getByRole("button", { name: "Submit reply" }));

    await waitFor(() => expect(screen.getByText(/server error/i)).toBeInTheDocument());
    expect((screen.getByPlaceholderText("Write a reply…") as HTMLTextAreaElement).value).toBe("Keep me on failure");
  });
});
