import type { AgentProfile } from "../api/types";

export interface AgentReadiness {
  canReceive: boolean;
  /** A structural configuration problem, if any. Null when setup is complete. */
  setupIssue: string | null;
  /** A short human-readable explanation for the agent's routing state. */
  detail: string;
}

const AVAILABILITY_LABELS: Record<AgentProfile["availability_status"], string> = {
  available: "Available",
  paused: "Paused",
  offline: "Offline",
};

/**
 * Explain whether an agent can receive work and, when not, why.
 *
 * A newly created agent role starts with a non-routing profile (OFFLINE, no
 * department, zero capacity). Callers must never present that as ready for
 * work; they should surface `setupIssue` to the staff member.
 */
export function agentReadiness(profile: AgentProfile | null | undefined): AgentReadiness {
  if (!profile) {
    return {
      canReceive: false,
      setupIssue: "No routing profile exists yet. Save a department and capacity.",
      detail: "Profile setup required",
    };
  }
  if (!profile.department_id) {
    return {
      canReceive: false,
      setupIssue: "Assign an active department before this agent can receive work.",
      detail: "Profile setup required",
    };
  }
  if (profile.availability_status !== "available") {
    return {
      canReceive: false,
      setupIssue: `Set availability to Available (currently ${AVAILABILITY_LABELS[profile.availability_status]}).`,
      detail: `Profile setup required · ${AVAILABILITY_LABELS[profile.availability_status]}`,
    };
  }
  if (profile.max_active_tickets <= 0) {
    return {
      canReceive: false,
      setupIssue: "Set a capacity above zero so the agent can be assigned work.",
      detail: "Profile setup required",
    };
  }
  if (!profile.can_receive_new_tickets) {
    return {
      canReceive: false,
      setupIssue: null,
      detail:
        profile.current_active_tickets >= profile.max_active_tickets
          ? "At capacity"
          : "Profile setup required",
    };
  }
  return {
    canReceive: true,
    setupIssue: null,
    detail: `Eligible · ${profile.current_active_tickets}/${profile.max_active_tickets}`,
  };
}
