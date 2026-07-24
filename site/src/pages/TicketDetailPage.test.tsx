import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AnalysisResult, Ticket } from "../api/types";
import { allowedTransitions, AnalysisCard } from "./TicketDetailPage";

const ticket: Ticket = {
  id: "ticket-1",
  title: "Test",
  description: "Description",
  category: "API_Error",
  tags: [],
  department_id: "department-1",
  skill_ids: [],
  assigned_agent_id: "agent-1",
  creator_user_id: "customer-1",
  status: "In progress",
  priority: 2,
  updated_at: "2026-01-01T00:00:00Z",
  created_at: "2026-01-01T00:00:00Z",
  due_at: null,
  is_overdue: false,
  deleted_at: null,
};

const analysis: AnalysisResult = {
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
  requester_id: "agent-1",
  attempt_count: 1,
  created_at: "2026-07-24T03:00:00Z",
  started_at: null,
  completed_at: null,
  updated_at: "2026-07-24T03:00:00Z",
  status: "pending",
};

describe("role-aware ticket transitions", () => {
  it("shows normal work transitions only to the assigned agent", () => {
    expect(allowedTransitions(ticket, "agent", "agent-1")).toEqual([
      "Pending",
      "On hold",
      "Resolved",
    ]);
    expect(allowedTransitions(ticket, "agent", "other-agent")).toEqual([]);
  });

  it("only lets a customer close a resolved own ticket or reopen a closed own ticket", () => {
    expect(
      allowedTransitions({ ...ticket, status: "Resolved" }, "user", "customer-1"),
    ).toEqual(["Closed"]);
    expect(
      allowedTransitions({ ...ticket, status: "Resolved" }, "user", "another-customer"),
    ).toEqual([]);
  });

  it("does not offer the dedicated start-work transition as a generic manager patch", () => {
    expect(allowedTransitions({ ...ticket, status: "Open" }, "manager", "manager-1")).toEqual(
      [],
    );
  });
});

describe("analysis states", () => {
  it.each([
    ["pending", "Pending analysis"],
    ["running", "Analyzing ticket"],
  ] as const)("renders the %s worker state", (status, label) => {
    render(
      <AnalysisCard
        result={{ ...analysis, status }}
        busy={false}
        onRun={vi.fn()}
      />,
    );

    expect(screen.getByText(new RegExp(label))).toBeInTheDocument();
  });

  it("renders a safe failure with an available retry", () => {
    render(
      <AnalysisCard
        result={{
          ...analysis,
          status: "failed",
          error_code: "worker_unavailable",
          error_message: "The analysis worker is unavailable.",
        }}
        busy={false}
        onRun={vi.fn()}
      />,
    );

    expect(screen.getByText("Analysis failed")).toBeInTheDocument();
    expect(screen.getByText("The analysis worker is unavailable.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeEnabled();
  });
});
