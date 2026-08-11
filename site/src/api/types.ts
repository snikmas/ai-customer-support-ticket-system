export type Role =
  | "super_admin"
  | "admin"
  | "manager"
  | "agent"
  | "agent_readonly"
  | "user"
  | "guest"
  | "bot"
  | "api";

export type TicketStatus =
  | "New"
  | "Open"
  | "Pending"
  | "In progress"
  | "On hold"
  | "Resolved"
  | "Closed"
  | "Reopened";

export type Priority = 1 | 2 | 3 | 4;
export type AnalysisStatus = "pending" | "running" | "completed" | "failed";
export type Visibility = "Public" | "Internal" | "Private To Manager";

export const TICKET_STATUSES: TicketStatus[] = [
  "New",
  "Open",
  "Pending",
  "In progress",
  "On hold",
  "Resolved",
  "Closed",
  "Reopened",
];

export const CATEGORIES = [
  "API_Error",
  "Authentication",
  "Model Output",
  "Rag Retrieval",
  "Agent Workflow",
  "Performance",
  "Billing",
  "Account Access",
  "Documentation",
  "Feature Request",
] as const;

export const TAGS = [
  "api-key",
  "jwt",
  "rate-limit",
  "timeout",
  "500-error",
  "400-error",
  "streaming",
  "chat",
  "embeddings",
  "rag",
  "vector-search",
  "file-upload",
  "bad-answer",
  "hallucination",
  "latency",
  "cost",
  "usage-limit",
  "python",
  "javascript",
  "fastapi",
  "postgres",
  "redis",
  "docker",
] as const;

export type Category = (typeof CATEGORIES)[number];
export type Tag = (typeof TAGS)[number];

export interface Tokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface SessionIdentity {
  userId: string;
  role: Role;
}

export interface User {
  id: string;
  nickname: string;
  avatar_url: string | null;
  first_name: string;
  last_name: string;
  phone: string;
  email: string;
  role: Role;
  updated_at: string;
  created_at: string;
  deleted_at: string | null;
  user_status: "Active" | "Deleted" | "Banned";
  agent_profile?: AgentProfile | null;
}

export interface AgentProfile {
  user_id: string;
  availability_status: "available" | "paused" | "offline";
  availability_reason: string | null;
  availability_note: string | null;
  unavailable_until: string | null;
  max_active_tickets: number;
  last_assigned_at: string | null;
  department_id: string | null;
  skill_ids: string[];
  current_active_tickets: number;
  can_receive_new_tickets: boolean;
  created_at: string;
  updated_at: string;
}

export interface TicketCustomerSummary {
  user_id: string;
  display_name: string;
  nickname: string;
  account_status: "Active" | "Deleted" | "Banned";
  email: string | null;
  phone: string | null;
  avatar_url: string | null;
}

export interface Ticket {
  id: string;
  title: string;
  description: string;
  category: Category;
  tags: Tag[];
  department_id: string | null;
  skill_ids: string[];
  assigned_agent_id: string | null;
  creator_user_id: string;
  status: TicketStatus;
  priority: Priority;
  updated_at: string;
  created_at: string;
  due_at: string | null;
  is_overdue: boolean;
  deleted_at: string | null;
}

export interface RelatedTicket {
  link_id: string;
  ticket_id: string;
  title: string;
  status: TicketStatus;
  priority: Priority;
  created_at: string;
}

export interface RoutingCatalog {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface Comment {
  id: string;
  ticket_id: string;
  author_user_id: string;
  body: string;
  visibility: Visibility;
  edited_at: string | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  deleted_by_user_id: string | null;
  parent_comment_id: string | null;
  attachments_count: number | null;
  source: "Web" | "API" | "Email" | "Bot" | "System";
}

export interface Attachment {
  id: string;
  comment_id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
}

export interface Notification {
  id: string;
  notification_type: string;
  ticket_id: string | null;
  message: string;
  created_at: string;
  read_at: string | null;
}

export interface HistoryEvent {
  id: string;
  entity_type: string;
  entity_id: string | null;
  actor_type: "human" | "system";
  actor_user_id: string | null;
  event_type: string;
  old_value: Record<string, unknown> | null;
  new_value: Record<string, unknown>;
  metadata: string | null;
  created_at: string;
}

export interface AnalysisResult {
  id: string;
  summary: string | null;
  error_code: string | null;
  error_message: string | null;
  ticket_id: string | null;
  job_id: string | null;
  provider: string | null;
  model: string | null;
  prompt_version: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  requester_id: string | null;
  attempt_count: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string;
  status: AnalysisStatus;
}

export interface ApiErrorBody {
  error?: {
    code?: string;
    message?: string;
    details?: unknown;
  };
}

export const PRIORITY_LABELS: Record<Priority, string> = {
  1: "Low",
  2: "Normal",
  3: "High",
  4: "Critical",
};

export const STAFF_ROLES: Role[] = [
  "agent_readonly",
  "agent",
  "manager",
  "admin",
  "super_admin",
];

export const MANAGER_ROLES: Role[] = ["manager", "admin", "super_admin"];

export const STATUS_TRANSITIONS: Record<TicketStatus, TicketStatus[]> = {
  New: ["Open"],
  Open: ["In progress"],
  "In progress": ["Pending", "On hold", "Resolved"],
  Pending: ["In progress", "Resolved"],
  "On hold": ["In progress"],
  Resolved: ["Closed", "In progress"],
  Closed: ["Reopened"],
  Reopened: ["In progress"],
};
