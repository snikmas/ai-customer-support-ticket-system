import { ApiError } from "../api/client";

export interface ValidationIssue {
  /** Raw location path from the API, e.g. ["body", "email"] or ["query", "priority"]. */
  location: string[];
  /** The offending field name, when the API scoped the error to one. */
  field: string | null;
  /** A short, actionable message safe to show next to the field. */
  message: string;
}

const FIELD_MESSAGES: Record<string, string> = {
  email: "Enter a valid email address.",
  phone: "Enter a valid phone number.",
  password: "Choose a password that meets the length requirement.",
  first_name: "Enter a first name.",
  last_name: "Enter a last name.",
  nickname: "Enter a unique nickname.",
};

function humanize(field: string | null, raw: string): string {
  if (field && FIELD_MESSAGES[field]) return FIELD_MESSAGES[field];
  const text = raw.trim();
  if (!text) return "This value is not accepted.";
  const sentence = text[0].toUpperCase() + text.slice(1);
  return /[.!?]$/.test(sentence) ? sentence : `${sentence}.`;
}

/**
 * Read the backend's structured 422 details without trusting their shape.
 * Unknown or non-JSON failures fall back to an empty list, so callers keep the
 * generic error message instead of crashing.
 */
export function validationIssues(error: unknown): ValidationIssue[] {
  if (!(error instanceof ApiError) || !Array.isArray(error.details)) return [];
  const issues: ValidationIssue[] = [];
  for (const entry of error.details) {
    if (!entry || typeof entry !== "object") continue;
    const record = entry as { loc?: unknown; msg?: unknown };
    if (!Array.isArray(record.loc) || record.loc.length === 0) continue;
    const location = record.loc.map((part) => String(part));
    const field = location.length > 1 ? location[location.length - 1] : null;
    const raw = typeof record.msg === "string" ? record.msg : "Invalid value";
    issues.push({ location, field, message: humanize(field, raw) });
  }
  return issues;
}

/** Group issues by the field the user can correct, keeping the first message. */
export function fieldIssues(
  issues: ValidationIssue[],
  scope: "body" | "query" | "path",
): Record<string, string> {
  const grouped: Record<string, string> = {};
  for (const issue of issues) {
    if (issue.location[0] !== scope || !issue.field) continue;
    if (!grouped[issue.field]) grouped[issue.field] = issue.message;
  }
  return grouped;
}
