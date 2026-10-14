import type { HistoryEvent, Priority } from "../api/types";
import { PRIORITY_LABELS } from "../api/types";

function actorLabel(event: HistoryEvent): string {
  if (event.actor_display_name) return event.actor_display_name;
  return event.actor_type === "system" ? "System" : "Unknown user";
}

function priorityText(value: unknown): string | null {
  if (typeof value !== "number") return null;
  return PRIORITY_LABELS[value as Priority] ?? `Priority ${value}`;
}

function assignmentText(
  value: Record<string, unknown>,
  nameById?: Map<string, string>,
): string {
  const agentId = typeof value.assigned_agent_id === "string" ? value.assigned_agent_id : null;
  if (!agentId) return "Assignment cleared";
  const name = nameById?.get(agentId);
  return name ? `Assigned to ${name}` : "Assignment updated";
}

/**
 * Turn the stored audit snapshot into a readable sentence. Missing old values
 * and unknown event types degrade to a short generic line instead of crashing.
 */
export function formatHistoryEvent(
  event: HistoryEvent,
  nameById?: Map<string, string>,
): string {
  const old = event.old_value ?? {};
  const next = event.new_value ?? {};

  switch (event.event_type) {
    case "Ticket Created":
      return "Ticket created";
    case "Ticket Status Changed": {
      const from = typeof old.status === "string" ? old.status : undefined;
      const to = typeof next.status === "string" ? next.status : undefined;
      if (from && to) return `Status changed from ${from} to ${to}`;
      if (to) return `Status changed to ${to}`;
      return "Status changed";
    }
    case "Ticket Updated": {
      const parts: string[] = [];
      const priority = priorityText(next.priority);
      if (priority) parts.push(`Priority set to ${priority}`);
      if ("assigned_agent_id" in next) parts.push(assignmentText(next, nameById));
      if ("department_id" in next || "skill_ids" in next) parts.push("Routing updated");
      if ("tags" in next) parts.push("Tags updated");
      if ("due_at" in next && priority === null && !("status" in next)) {
        parts.push("SLA deadline updated");
      }
      return parts.join(" · ") || "Ticket updated";
    }
    case "Ticket Claimed":
      return "Ticket claimed";
    case "Ticket Assigned":
      return assignmentText(next, nameById);
    case "Ticket Reassigned":
      return `Reassigned · ${assignmentText(next, nameById)}`;
    case "Ticket Linked":
      return "Related ticket linked";
    case "Ticket Unlinked":
      return "Related ticket unlinked";
    case "Comment Created":
      return "Comment added";
    case "Comment Updated":
      return "Comment edited";
    case "Comment Deleted":
      return "Comment deleted";
    case "Attachment Added":
      return "Attachment added";
    case "Attachment Deleted":
      return "Attachment removed";
    case "Ticket Overdue":
      return "Ticket became overdue";
    default:
      return event.event_type || "Activity";
  }
}

export function historyActor(event: HistoryEvent): string {
  return actorLabel(event);
}
