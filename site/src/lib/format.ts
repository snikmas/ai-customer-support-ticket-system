import type { Category, Priority, Role } from "../api/types";
import { PRIORITY_LABELS } from "../api/types";

// Display labels only. Request values and stored enum values stay unchanged.
const CATEGORY_LABELS: Record<Category, string> = {
  API_Error: "API error",
  Authentication: "Authentication",
  "Model Output": "Model output",
  "Rag Retrieval": "RAG retrieval",
  "Agent Workflow": "Agent workflow",
  Performance: "Performance",
  Billing: "Billing",
  "Account Access": "Account access",
  Documentation: "Documentation",
  "Feature Request": "Feature request",
};

const ROLE_LABELS: Record<Role, string> = {
  super_admin: "Super admin",
  admin: "Admin",
  manager: "Manager",
  agent: "Agent",
  agent_readonly: "Read-only agent",
  user: "Customer",
  guest: "Guest",
  bot: "Bot",
  api: "API",
};

export function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function relativeTime(value: string): string {
  const seconds = Math.round((new Date(value).getTime() - Date.now()) / 1000);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  const ranges: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ["year", 31_536_000],
    ["month", 2_592_000],
    ["day", 86_400],
    ["hour", 3_600],
    ["minute", 60],
  ];
  for (const [unit, size] of ranges) {
    if (Math.abs(seconds) >= size) return formatter.format(Math.round(seconds / size), unit);
  }
  return formatter.format(seconds, "second");
}

export function priorityLabel(priority: Priority): string {
  return PRIORITY_LABELS[priority];
}

export function roleLabel(role: Role): string {
  return ROLE_LABELS[role] ?? role;
}

export function categoryLabel(category: Category): string {
  return CATEGORY_LABELS[category] ?? category;
}

export function initials(firstName?: string, lastName?: string): string {
  return `${firstName?.[0] ?? ""}${lastName?.[0] ?? ""}`.toUpperCase() || "?";
}
