import {
  AlertCircle,
  AlertTriangle,
  ChevronLeft,
  Clock,
  Lock,
  Paperclip,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiRequest, toErrorMessage } from "../api/client";
import {
  MANAGER_ROLES,
  PRIORITY_LABELS,
  STATUS_TRANSITIONS,
  type AnalysisResult,
  type Comment,
  type HistoryEvent,
  type Priority,
  type RoutingCatalog,
  type Ticket,
  type TicketStatus,
  type User,
  type Visibility,
} from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { StatePanel } from "../components/StatePanel";
import { UnsupportedButton } from "../components/UnsupportedButton";
import { useToast } from "../components/ToastContext";
import { formatDate, initials, priorityLabel, relativeTime, roleLabel } from "../lib/format";

interface DetailData {
  ticket: Ticket;
  comments: Comment[];
  history: HistoryEvent[];
  departments: RoutingCatalog[];
  skills: RoutingCatalog[];
}

export function TicketDetailPage() {
  const { ticketId = "" } = useParams();
  const navigate = useNavigate();
  const { identity, user } = useAuth();
  const { notify } = useToast();
  const [data, setData] = useState<DetailData | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [analyses, setAnalyses] = useState<AnalysisResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [mutationError, setMutationError] = useState("");
  const [busy, setBusy] = useState("");
  const [commentBody, setCommentBody] = useState("");
  const [visibility, setVisibility] = useState<Visibility>("Public");
  const [selectedAgent, setSelectedAgent] = useState("");
  const [selectedDepartment, setSelectedDepartment] = useState("");
  const [selectedSkillIds, setSelectedSkillIds] = useState<string[]>([]);

  const role = identity?.role;
  const isManager = Boolean(role && MANAGER_ROLES.includes(role));
  const isAgent = role === "agent";
  const isReadonly = role === "agent_readonly";
  const isCustomer = role === "user";

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [ticket, comments, history, departments, skills] = await Promise.all([
        apiRequest<Ticket>(`/tickets/${ticketId}`),
        apiRequest<Comment[]>(`/tickets/${ticketId}/comments?limit=100&sort_order=asc`),
        apiRequest<HistoryEvent[]>(`/tickets/${ticketId}/history?limit=100`),
        apiRequest<RoutingCatalog[]>("/departments/"),
        apiRequest<RoutingCatalog[]>("/skills/"),
      ]);
      setData({ ticket, comments, history, departments, skills });
      setSelectedDepartment(ticket.department_id ?? departments[0]?.id ?? "");
      setSelectedSkillIds(ticket.skill_ids);

      const maySeeAnalysis =
        isManager || (isAgent && ticket.assigned_agent_id === identity?.userId);
      const optionalRequests: Promise<void>[] = [];
      if (maySeeAnalysis) {
        optionalRequests.push(
          apiRequest<AnalysisResult[]>(`/tickets/${ticketId}/analysis-results?limit=20`)
            .then(setAnalyses)
            .catch(() => setAnalyses([])),
        );
      } else {
        setAnalyses([]);
      }
      if (isManager) {
        optionalRequests.push(
          apiRequest<User[]>("/users/?limit=100&sort_by=first_name&sort_order=asc")
            .then((items) => {
              setUsers(items);
              const firstAgent = items.find((item) => item.role === "agent");
              if (firstAgent) setSelectedAgent(firstAgent.id);
            })
            .catch(() => setUsers([])),
        );
      } else {
        setUsers(user ? [user] : []);
      }
      await Promise.all(optionalRequests);
    } catch (caught) {
      setError(toErrorMessage(caught));
    } finally {
      setLoading(false);
    }
  }, [identity?.userId, isAgent, isManager, ticketId, user]);

  useEffect(() => void load(), [load]);

  const activeAnalysis = analyses.find(
    (item) => item.status === "pending" || item.status === "running",
  );
  useEffect(() => {
    if (!activeAnalysis) return;
    const timer = window.setInterval(() => {
      apiRequest<AnalysisResult>(`/analysis-results/${activeAnalysis.id}`)
        .then((updated) => {
          setAnalyses((items) =>
            items.map((item) => (item.id === updated.id ? updated : item)),
          );
        })
        .catch(() => window.clearInterval(timer));
    }, 2000);
    return () => window.clearInterval(timer);
  }, [activeAnalysis]);

  const perform = async (label: string, action: () => Promise<unknown>) => {
    setBusy(label);
    setMutationError("");
    try {
      await action();
      await load();
      notify(`${label} completed.`);
    } catch (caught) {
      setMutationError(toErrorMessage(caught));
    } finally {
      setBusy("");
    }
  };

  if (loading) {
    return <StatePanel kind="loading" title="Loading ticket" message="Loading the ticket, conversation, and history…" />;
  }
  if (error || !data) {
    return (
      <StatePanel
        kind="error"
        title="Ticket could not be loaded"
        message={error || "The ticket is missing or unavailable."}
        action={
          <button className="button secondary" onClick={() => void load()}>
            Try again
          </button>
        }
      />
    );
  }

  const { ticket, comments, history, departments, skills } = data;
  const department = departments.find((item) => item.id === ticket.department_id);
  const skillNames = ticket.skill_ids.map(
    (id) => skills.find((item) => item.id === id)?.name || "Unknown skill",
  );
  const userMap = new Map(users.map((item) => [item.id, item]));
  if (user) userMap.set(user.id, user);
  const assignedAgent = ticket.assigned_agent_id
    ? userMap.get(ticket.assigned_agent_id)
    : undefined;
  const agents = users.filter((item) => item.role === "agent" && item.user_status === "Active");
  const canClaim = isAgent && ticket.status === "New" && !ticket.assigned_agent_id;
  const canStart =
    isAgent &&
    ticket.status === "Open" &&
    ticket.assigned_agent_id === identity?.userId;
  const canAnalyze =
    isManager || (isAgent && ticket.assigned_agent_id === identity?.userId);
  const canConfigureRouting =
    isManager && ticket.status === "New" && !ticket.assigned_agent_id;
  const canComment =
    !isReadonly &&
    (isManager ||
      (isAgent && ticket.assigned_agent_id === identity?.userId) ||
      (isCustomer && ticket.creator_user_id === identity?.userId));
  const transitions = allowedTransitions(ticket, role, identity?.userId);
  const latestAnalysis = analyses[0];

  async function addComment(event: FormEvent) {
    event.preventDefault();
    if (!commentBody.trim()) return;
    await perform("Comment", async () => {
      await apiRequest(`/tickets/${ticket.id}/comments`, {
        method: "POST",
        body: { body: commentBody.trim(), visibility },
      });
      setCommentBody("");
    });
  }

  return (
    <>
      <button className="back-link" onClick={() => navigate("/tickets")}>
        <ChevronLeft size={17} /> All tickets
      </button>
      <div className="detail-heading">
        <div>
          <p className="eyebrow">Ticket #{ticket.id.slice(0, 8)}</p>
          <h1>{ticket.title}</h1>
        </div>
        <span className={`status status-${ticket.status.toLowerCase().replaceAll(" ", "-")}`}>
          {ticket.status}
        </span>
      </div>
      {mutationError && (
        <div className="alert error" role="alert">
          <AlertCircle size={17} /> {mutationError}
        </div>
      )}

      <div className="detail-grid">
        <div className="detail-main">
          <section className="card description-card">
            <h2>Description</h2>
            <p>{ticket.description}</p>
          </section>

          {canAnalyze && (
            <AnalysisCard
              result={latestAnalysis}
              busy={busy === "Analysis"}
              onRun={() =>
                void perform("Analysis", async () => {
                  const result = await apiRequest<AnalysisResult>(
                    `/tickets/${ticket.id}/analysis-results`,
                    { method: "POST" },
                  );
                  setAnalyses((items) => [
                    result,
                    ...items.filter((item) => item.id !== result.id),
                  ]);
                })
              }
            />
          )}

          <section className="card tabs-card">
            <div className="tab-row">
              <button className="active">Activity</button>
              <UnsupportedButton feature="Customer Info">Customer Info</UnsupportedButton>
              <UnsupportedButton feature="Related Issues">Related Issues</UnsupportedButton>
            </div>
            <div className="comment-list">
              {comments.length === 0 ? (
                <p className="muted">No comments yet.</p>
              ) : (
                comments.map((comment) => {
                  const author = userMap.get(comment.author_user_id);
                  return (
                    <article
                      key={comment.id}
                      className={`comment comment-${comment.visibility.toLowerCase().replaceAll(" ", "-")}`}
                    >
                      <div className="avatar small">
                        {author
                          ? initials(author.first_name, author.last_name)
                          : comment.author_user_id.slice(0, 2).toUpperCase()}
                      </div>
                      <div>
                        <header>
                          <strong>
                            {author
                              ? `${author.first_name} ${author.last_name}`
                              : `User ${comment.author_user_id.slice(0, 8)}`}
                          </strong>
                          {comment.visibility !== "Public" && (
                            <span className="visibility">
                              <Lock size={12} /> {comment.visibility}
                            </span>
                          )}
                          <time title={formatDate(comment.created_at)}>
                            {relativeTime(comment.created_at)}
                          </time>
                        </header>
                        <p>{comment.body}</p>
                      </div>
                    </article>
                  );
                })
              )}
            </div>
            {canComment && (
              <form className="reply-form" onSubmit={(event) => void addComment(event)}>
                <div className="reply-toolbar">
                  <select
                    aria-label="Comment visibility"
                    value={visibility}
                    onChange={(event) => setVisibility(event.target.value as Visibility)}
                  >
                    <option value="Public">Public reply</option>
                    {!isCustomer && <option value="Internal">Internal note</option>}
                    {isManager && <option value="Private To Manager">Manager note</option>}
                  </select>
                </div>
                <textarea
                  rows={4}
                  value={commentBody}
                  onChange={(event) => setCommentBody(event.target.value)}
                  placeholder="Write a reply…"
                />
                <footer>
                  <UnsupportedButton
                    feature="Attachments"
                    className="icon-button"
                    aria-label="Attach a file"
                  >
                    <Paperclip size={17} />
                  </UnsupportedButton>
                  <button
                    className="button primary"
                    disabled={!commentBody.trim() || busy === "Comment"}
                  >
                    {busy === "Comment" ? "Submitting…" : "Submit reply"}
                  </button>
                </footer>
              </form>
            )}
          </section>

          <section className="card history-card">
            <h2>Activity timeline</h2>
            {history.length === 0 ? (
              <p className="muted">No visible history events.</p>
            ) : (
              <ol>
                {history.map((event) => (
                  <li key={event.id}>
                    <i />
                    <div>
                      <strong>{event.event_type}</strong>
                      <span>{formatDate(event.created_at)}</span>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>

        <aside className="detail-side">
          <section className="card action-card">
            <h2>Actions</h2>
            {isReadonly && <p className="muted">This role has read-only access.</p>}
            {canConfigureRouting && (
              <div className="routing-controls">
                <strong>Route ticket</strong>
                <p className="muted">
                  Choose the internal destination after reviewing the customer request.
                </p>
                {departments.length === 0 ? (
                  <p className="muted">No active departments are configured.</p>
                ) : (
                  <>
                    <label>
                      Department
                      <select
                        value={selectedDepartment}
                        onChange={(event) => setSelectedDepartment(event.target.value)}
                      >
                        {departments.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    {skills.length > 0 && (
                      <fieldset>
                        <legend>Required skills</legend>
                        <div>
                          {skills.map((skill) => (
                            <label key={skill.id}>
                              <input
                                type="checkbox"
                                checked={selectedSkillIds.includes(skill.id)}
                                onChange={(event) =>
                                  setSelectedSkillIds((current) =>
                                    event.target.checked
                                      ? [...current, skill.id]
                                      : current.filter((id) => id !== skill.id),
                                  )
                                }
                              />
                              {skill.name}
                            </label>
                          ))}
                        </div>
                      </fieldset>
                    )}
                    <button
                      className="button primary full-width"
                      disabled={!selectedDepartment || Boolean(busy)}
                      onClick={() =>
                        void perform("Routing", () =>
                          apiRequest(`/tickets/${ticket.id}`, {
                            method: "PATCH",
                            body: {
                              department_id: selectedDepartment,
                              skill_ids: selectedSkillIds,
                            },
                          }),
                        )
                      }
                    >
                      Save routing
                    </button>
                  </>
                )}
              </div>
            )}
            {canClaim && (
              <button
                className="button secondary full-width"
                disabled={Boolean(busy)}
                onClick={() =>
                  void perform("Claim ticket", () =>
                    apiRequest(`/tickets/${ticket.id}/claim`, { method: "POST" }),
                  )
                }
              >
                Claim ticket
              </button>
            )}
            {isManager && agents.length > 0 && ticket.department_id && (
              <div className="inline-action">
                <select value={selectedAgent} onChange={(event) => setSelectedAgent(event.target.value)}>
                  {agents.map((agent) => (
                    <option key={agent.id} value={agent.id}>
                      {agent.first_name} {agent.last_name}
                    </option>
                  ))}
                </select>
                <button
                  className="button secondary"
                  disabled={!selectedAgent || Boolean(busy)}
                  onClick={() =>
                    void perform("Assignment", () =>
                      apiRequest(`/tickets/${ticket.id}/assign`, {
                        method: "POST",
                        body: { agent_id: selectedAgent },
                      }),
                    )
                  }
                >
                  Assign
                </button>
              </div>
            )}
            {canStart && (
              <button
                className="button primary full-width"
                disabled={Boolean(busy)}
                onClick={() =>
                  void perform("Start work", () =>
                    apiRequest(`/tickets/${ticket.id}/start-work`, { method: "POST" }),
                  )
                }
              >
                Start work
              </button>
            )}
            {transitions.length > 0 && (
              <div className="action-buttons">
                {transitions.map((status) => (
                  <button
                    key={status}
                    className={status === "Resolved" ? "button success" : "button secondary"}
                    disabled={Boolean(busy)}
                    onClick={() =>
                      void perform(`Status changed to ${status}`, () =>
                        apiRequest(`/tickets/${ticket.id}`, {
                          method: "PATCH",
                          body: { status },
                        }),
                      )
                    }
                  >
                    {status === "Resolved" ? "Resolve" : `Move to ${status}`}
                  </button>
                ))}
              </div>
            )}
            {isManager && (
              <label>
                Priority
                <select
                  value={ticket.priority}
                  disabled={Boolean(busy)}
                  onChange={(event) =>
                    void perform("Priority update", () =>
                      apiRequest(`/tickets/${ticket.id}`, {
                        method: "PATCH",
                        body: { priority: Number(event.target.value) as Priority },
                      }),
                    )
                  }
                >
                  {([4, 3, 2, 1] as Priority[]).map((value) => (
                    <option key={value} value={value}>
                      {PRIORITY_LABELS[value]}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {!canClaim && !canStart && transitions.length === 0 && !isManager && !isReadonly && (
              <p className="muted">No workflow action is available for this ticket state.</p>
            )}
          </section>

          <section className="card info-card">
            <h2>Ticket info</h2>
            <dl>
              <div>
                <dt>Priority</dt>
                <dd className={`priority priority-${ticket.priority}`}>
                  <i /> {priorityLabel(ticket.priority)}
                </dd>
              </div>
              <div>
                <dt>Department</dt>
                <dd>{ticket.department_id ? department?.name || "Unknown" : "Awaiting triage"}</dd>
              </div>
              <div>
                <dt>Assignee</dt>
                <dd>
                  {assignedAgent
                    ? `${assignedAgent.first_name} ${assignedAgent.last_name}`
                    : ticket.assigned_agent_id
                      ? ticket.assigned_agent_id.slice(0, 8)
                      : "Unassigned"}
                </dd>
              </div>
              <div>
                <dt>Category</dt>
                <dd>{ticket.category.replaceAll("_", " ")}</dd>
              </div>
              <div>
                <dt>Created</dt>
                <dd>{formatDate(ticket.created_at)}</dd>
              </div>
              <div>
                <dt>Updated</dt>
                <dd>{formatDate(ticket.updated_at)}</dd>
              </div>
            </dl>
            {skillNames.length > 0 && (
              <div className="chip-section">
                <span>Required skills</span>
                <div>{skillNames.map((name) => <b key={name}>{name}</b>)}</div>
              </div>
            )}
            {ticket.tags.length > 0 && (
              <div className="chip-section">
                <span>Tags</span>
                <div>{ticket.tags.map((tag) => <b key={tag}>{tag}</b>)}</div>
              </div>
            )}
            <div className={`sla-box ${ticket.is_overdue ? "sla-overdue" : ""}`}>
              <span>SLA deadline</span>
              <strong>{formatDate(ticket.due_at)}</strong>
              {ticket.is_overdue && (
                <em>
                  <AlertTriangle size={14} /> Overdue
                </em>
              )}
            </div>
          </section>
        </aside>
      </div>
    </>
  );
}

export function allowedTransitions(
  ticket: Ticket,
  role: string | undefined,
  userId: string | undefined,
): TicketStatus[] {
  const options = STATUS_TRANSITIONS[ticket.status] ?? [];
  if (role === "user") {
    if (ticket.creator_user_id !== userId) return [];
    return options.filter(
      (status) =>
        (ticket.status === "Resolved" && status === "Closed") ||
        (ticket.status === "Closed" && status === "Reopened"),
    );
  }
  if (role === "agent") {
    if (ticket.assigned_agent_id !== userId) return [];
    return options.filter(
      (status) =>
        !(ticket.status === "Open" && status === "In progress") &&
        !(ticket.status === "New" && status === "Open"),
    );
  }
  if (role && MANAGER_ROLES.includes(role as never)) {
    return options.filter(
      (status) =>
        !(ticket.status === "Open" && status === "In progress") &&
        !(ticket.status === "New" && status === "Open"),
    );
  }
  return [];
}

export function AnalysisCard({
  result,
  busy,
  onRun,
}: {
  result?: AnalysisResult;
  busy: boolean;
  onRun: () => void;
}) {
  return (
    <section className={`card analysis-card analysis-${result?.status ?? "empty"}`}>
      <header>
        <span>
          <Sparkles size={17} /> <strong>AI ticket summary</strong>
        </span>
        {result?.provider && (
          <small>
            {result.provider} · {result.model || "configured model"}
          </small>
        )}
      </header>
      {!result ? (
        <div className="analysis-body centered">
          <p>No analysis has been requested for this ticket.</p>
          <button className="button primary" disabled={busy} onClick={onRun}>
            {busy ? "Requesting…" : "Run analysis"}
          </button>
        </div>
      ) : result.status === "pending" ? (
        <div className="analysis-body centered">
          <Clock size={22} />
          <strong>Pending analysis</strong>
          <p>Waiting for an RQ worker to pick up this ticket.</p>
        </div>
      ) : result.status === "running" ? (
        <div className="analysis-body">
          <span className="running-label">
            <i /> Analyzing ticket…
          </span>
          <div className="progress">
            <span />
          </div>
          <p>The page polls the saved analysis result; you can safely navigate away.</p>
        </div>
      ) : result.status === "failed" ? (
        <div className="analysis-body analysis-failure">
          <AlertTriangle size={21} />
          <div>
            <strong>Analysis failed</strong>
            <p>{result.error_message || "The worker could not complete the analysis."}</p>
            {result.error_code && <code>{result.error_code}</code>}
          </div>
          <button className="button secondary" disabled={busy} onClick={onRun}>
            <RefreshCw size={15} /> Retry
          </button>
        </div>
      ) : (
        <div className="analysis-body">
          <p>{result.summary}</p>
          <footer>
            <span>
              Attempt {result.attempt_count} · {formatDate(result.completed_at)}
            </span>
            <button className="button secondary compact" disabled={busy} onClick={onRun}>
              Run new analysis
            </button>
          </footer>
        </div>
      )}
    </section>
  );
}
