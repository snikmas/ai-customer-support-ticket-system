import { describe, expect, it } from "vitest";
import type { AgentProfile } from "../api/types";
import { agentReadiness } from "./agents";

const base: AgentProfile = {
  user_id: "agent-1",
  availability_status: "available",
  availability_reason: null,
  availability_note: null,
  unavailable_until: null,
  max_active_tickets: 5,
  last_assigned_at: null,
  department_id: "support",
  skill_ids: [],
  current_active_tickets: 0,
  can_receive_new_tickets: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("agentReadiness", () => {
  it("marks a fully configured available agent eligible", () => {
    expect(agentReadiness(base)).toMatchObject({ canReceive: true, setupIssue: null });
  });

  it("treats a brand-new non-routing profile as incomplete and explains why", () => {
    const readiness = agentReadiness({
      ...base,
      availability_status: "offline",
      department_id: null,
      max_active_tickets: 0,
      can_receive_new_tickets: false,
    });

    expect(readiness.canReceive).toBe(false);
    expect(readiness.setupIssue).toMatch(/department/i);
  });

  it("explains an offline agent without calling the profile ready", () => {
    const readiness = agentReadiness({
      ...base,
      availability_status: "offline",
      can_receive_new_tickets: false,
    });

    expect(readiness.canReceive).toBe(false);
    expect(readiness.setupIssue).toMatch(/available/i);
  });

  it("explains zero capacity", () => {
    const readiness = agentReadiness({
      ...base,
      max_active_tickets: 0,
      can_receive_new_tickets: false,
    });

    expect(readiness.setupIssue).toMatch(/capacity/i);
  });

  it("distinguishes at-capacity from an incomplete profile", () => {
    const readiness = agentReadiness({
      ...base,
      current_active_tickets: 5,
      can_receive_new_tickets: false,
    });

    expect(readiness.setupIssue).toBeNull();
    expect(readiness.detail).toMatch(/capacity/i);
  });

  it("flags a missing profile entirely", () => {
    expect(agentReadiness(null).setupIssue).toBeTruthy();
  });
});
