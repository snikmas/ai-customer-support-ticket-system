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
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, apiRequest, downloadFile, toErrorMessage } from "../api/client";
import {
  MANAGER_ROLES,
  PRIORITY_LABELS,
  STATUS_TRANSITIONS,
  type AnalysisResult,
  type AssignmentCandidate,
  type Attachment,
  type Comment,
  type HistoryEvent,
  type Priority,
  type Role,
  type RoutingCatalog,
  type Ticket,
  type TicketCustomerSummary,
  type RelatedTicket,
  type TicketStatus,
  type User,
  type Visibility,
} from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { AttachmentList, failedPanel, loadedPanel, loadingPanel, type PanelState } from "../components/AttachmentList";
import { useDrafts } from "../components/DraftContext";
import { StatePanel } from "../components/StatePanel";
import { useToast } from "../components/ToastContext";
import { formatHistoryEvent, historyActor } from "../lib/history";
import { createLatestGuard } from "../lib/latest";
import { categoryLabel, formatDate, initials, priorityLabel, relativeTime, roleLabel } from "../lib/format";

const COMMENT_PAGE_SIZE = 50;
const HISTORY_PAGE_SIZE = 50;
const CANDIDATE_PAGE_SIZE = 20;
const MAX_POLL_RETRIES = 4;

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
  const { saveDraft, clearDraft } = useDrafts();
  const [data, setData] = useState<DetailData | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [analyses, setAnalyses] = useState<AnalysisResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [mutationError, setMutationError] = useState("");
  const [mutationConflict, setMutationConflict] = useState(false);
  const [busy, setBusy] = useState("");
  const [selectedAgent, setSelectedAgent] = useState("");
  const [selectedDepartment, setSelectedDepartment] = useState("");
  const [selectedSkillIds, setSelectedSkillIds] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState<"activity" | "customer" | "related">("activity");
  const [customer, setCustomer] = useState<TicketCustomerSummary | null>(null);
  const [customerLoading, setCustomerLoading] = useState(false);
  const [customerError, setCustomerError] = useState("");
  const [related, setRelated] = useState<RelatedTicket[]>([]);
  const [relatedCandidates, setRelatedCandidates] = useState<Ticket[]>([]);
  const [relatedSearch, setRelatedSearch] = useState("");
  const [relatedLoading, setRelatedLoading] = useState(false);
  const [relatedBusy, setRelatedBusy] = useState("");
  const [relatedError, setRelatedError] = useState("");
  const [attachmentsByComment, setAttachmentsByComment] = useState<
    Record<string, PanelState<Attachment>>
  >({});
  const [downloadingAttachment, setDownloadingAttachment] = useState("");
  const [commentsHasMore, setCommentsHasMore] = useState(false);
  const [commentsLoadingMore, setCommentsLoadingMore] = useState(false);
  const [historyHasMore, setHistoryHasMore] = useState(false);
  const [historyLoadingMore, setHistoryLoadingMore] = useState(false);
  const [candidates, setCandidates] = useState<AssignmentCandidate[]>([]);
  const [candidateSearch, setCandidateSearch] = useState("");
  const [candidatesLoading, setCandidatesLoading] = useState(false);
  const [candidatesError, setCandidatesError] = useState("");
  const [candidatesHasMore, setCandidatesHasMore] = useState(false);
  const [analysisPollError, setAnalysisPollError] = useState("");
  const [analysisPolling, setAnalysisPolling] = useState(false);

  // Every ticket-scoped request captures an epoch. A ticket change or a fresh
  // `load()` advances it, so a response for an old ticket can never overwrite
  // the panels of the ticket now on screen.
  const requestEpoch = useRef(0);
  const candidatesOffset = useRef(0);
  // Analysis attempts requested in this session. Only these may announce a
  // completion, so opening a ticket with an older completed result stays quiet.
  const watchedAnalyses = useRef<Set<string>>(new Set());
  const beginRequestEpoch = useCallback(() => ++requestEpoch.current, []);
  const snapshotRequestEpoch = useCallback(() => requestEpoch.current, []);
  const isCurrentEpoch = useCallback((epoch: number) => epoch === requestEpoch.current, []);

  const loadAttachments = useCallback(
    (targets: Comment[], epoch: number) => {
      setAttachmentsByComment((current) => {
        const next = { ...current };
        for (const comment of targets) {
          if (!next[comment.id] || next[comment.id].status === "error") {
            next[comment.id] = loadingPanel<Attachment>();
          }
        }
        return next;
      });
      for (const comment of targets) {
        apiRequest<Attachment[]>(
          `/tickets/${ticketId}/comments/${comment.id}/attachments`,
        )
          .then((items) => {
            if (isCurrentEpoch(epoch)) {
              setAttachmentsByComment((current) => ({
                ...current,
                [comment.id]: loadedPanel(items),
              }));
            }
          })
          .catch((caught) => {
            if (isCurrentEpoch(epoch)) {
              setAttachmentsByComment((current) => ({
                ...current,
                [comment.id]: failedPanel<Attachment>(toErrorMessage(caught)),
              }));
            }
          });
      }
    },
    [isCurrentEpoch, ticketId],
  );

  const loadCandidates = useCallback(
    async (
      departmentId: string | null,
      search: string,
      append: boolean,
      epoch: number,
    ) => {
      if (!departmentId) {
        setCandidates([]);
        setCandidatesHasMore(false);
        setCandidatesError("");
        return;
      }
      setCandidatesLoading(true);
      if (!append) setCandidatesError("");
      const offset = append ? candidatesOffset.current : 0;
      const query = new URLSearchParams({
        department_id: departmentId,
        limit: String(CANDIDATE_PAGE_SIZE),
        offset: String(offset),
      });
      if (search.trim()) query.set("search", search.trim());
      try {
        const page = await apiRequest<AssignmentCandidate[]>(
          `/users/assignment-candidates?${query}`,
        );
        if (!isCurrentEpoch(epoch)) return;
        candidatesOffset.current = offset + page.length;
        setCandidates((current) => (append ? [...current, ...page] : page));
        setCandidatesHasMore(page.length === CANDIDATE_PAGE_SIZE);
        setCandidatesError("");
        if (!append) {
          setSelectedAgent((current) =>
            page.some((candidate) => candidate.user_id === current)
              ? current
              : page[0]?.user_id ?? "",
          );
        }
      } catch (caught) {
        if (isCurrentEpoch(epoch)) setCandidatesError(toErrorMessage(caught));
      } finally {
        if (isCurrentEpoch(epoch)) setCandidatesLoading(false);
      }
    },
    [isCurrentEpoch],
  );

  const role = identity?.role;
  const isManager = Boolean(role && MANAGER_ROLES.includes(role));
  const isAgent = role === "agent";
  const isReadonly = role === "agent_readonly";
  const isCustomer = role === "user";

  // A ticket change makes every in-flight request for the previous ticket
  // stale. Running this effect before the loader effect bumps the epoch first.
  useEffect(() => {
    requestEpoch.current += 1;
    watchedAnalyses.current = new Set();
  }, [ticketId]);

  const load = useCallback(async (initial = false) => {
    const epoch = beginRequestEpoch();
    // Reserve the full-page loading state for the first load. Later refreshes
    // update in place so an in-progress composer is not unmounted mid-request.
    if (initial) setLoading(true);
    setError("");
    setMutationConflict(false);
    try {
      const [ticket, commentPage, historyPage, departments, skills] = await Promise.all([
        apiRequest<Ticket>(`/tickets/${ticketId}`),
        apiRequest<Comment[]>(
          `/tickets/${ticketId}/comments?limit=${COMMENT_PAGE_SIZE}&sort_order=desc`,
        ),
        apiRequest<HistoryEvent[]>(`/tickets/${ticketId}/history?limit=${HISTORY_PAGE_SIZE}`),
        apiRequest<RoutingCatalog[]>("/departments/"),
        apiRequest<RoutingCatalog[]>("/skills/"),
      ]);
      if (!isCurrentEpoch(epoch)) return;
      const comments = [...commentPage].reverse();
      setData({ ticket, comments, history: historyPage, departments, skills });
      setCommentsHasMore(commentPage.length === COMMENT_PAGE_SIZE);
      setHistoryHasMore(historyPage.length === HISTORY_PAGE_SIZE);
      setSelectedDepartment(ticket.department_id ?? departments[0]?.id ?? "");
      setSelectedSkillIds(ticket.skill_ids);
      loadAttachments(comments, epoch);

      const maySeeAnalysis =
        isManager || (isAgent && ticket.assigned_agent_id === identity?.userId);
      if (maySeeAnalysis) {
        apiRequest<AnalysisResult[]>(`/tickets/${ticketId}/analysis-results?limit=20`)
          .then((items) => {
            if (isCurrentEpoch(epoch)) setAnalyses(items);
          })
          .catch(() => {
            if (isCurrentEpoch(epoch)) setAnalyses([]);
          });
      } else {
        setAnalyses([]);
      }
      if (isManager) {
        apiRequest<User[]>("/users/?limit=100&sort_by=first_name&sort_order=asc")
          .then((items) => {
            if (isCurrentEpoch(epoch)) setUsers(items);
          })
          .catch(() => {
            if (isCurrentEpoch(epoch)) setUsers([]);
          });
        void loadCandidates(ticket.department_id, "", false, epoch);
      } else {
        setUsers(user ? [user] : []);
        setCandidates([]);
        setCandidatesError("");
      }
    } catch (caught) {
      if (isCurrentEpoch(epoch)) setError(toErrorMessage(caught));
    } finally {
      if (initial && isCurrentEpoch(epoch)) setLoading(false);
    }
  }, [
    beginRequestEpoch,
    identity?.userId,
    isAgent,
    isCurrentEpoch,
    isManager,
    loadAttachments,
    loadCandidates,
    ticketId,
    user,
  ]);

  useEffect(() => void load(true), [load]);

  const loadOlderComments = useCallback(async () => {
    const epoch = snapshotRequestEpoch();
    const loaded = data?.comments.length ?? 0;
    setCommentsLoadingMore(true);
    try {
      const page = await apiRequest<Comment[]>(
        `/tickets/${ticketId}/comments?limit=${COMMENT_PAGE_SIZE}&sort_order=desc&offset=${loaded}`,
      );
      if (!isCurrentEpoch(epoch)) return;
      const older = [...page].reverse();
      setData((current) =>
        current ? { ...current, comments: [...older, ...current.comments] } : current,
      );
      setCommentsHasMore(page.length === COMMENT_PAGE_SIZE);
      loadAttachments(older, epoch);
    } catch (caught) {
      if (isCurrentEpoch(epoch)) setMutationError(toErrorMessage(caught));
    } finally {
      if (isCurrentEpoch(epoch)) setCommentsLoadingMore(false);
    }
  }, [data?.comments.length, isCurrentEpoch, loadAttachments, snapshotRequestEpoch, ticketId]);

  const loadMoreHistory = useCallback(async () => {
    const epoch = snapshotRequestEpoch();
    const loaded = data?.history.length ?? 0;
    setHistoryLoadingMore(true);
    try {
      const page = await apiRequest<HistoryEvent[]>(
        `/tickets/${ticketId}/history?limit=${HISTORY_PAGE_SIZE}&offset=${loaded}`,
      );
      if (!isCurrentEpoch(epoch)) return;
      setData((current) =>
        current ? { ...current, history: [...current.history, ...page] } : current,
      );
      setHistoryHasMore(page.length === HISTORY_PAGE_SIZE);
    } catch (caught) {
      if (isCurrentEpoch(epoch)) setMutationError(toErrorMessage(caught));
    } finally {
      if (isCurrentEpoch(epoch)) setHistoryLoadingMore(false);
    }
  }, [data?.history.length, isCurrentEpoch, snapshotRequestEpoch, ticketId]);

  const retryAttachment = useCallback(
    (commentId: string) => {
      const epoch = snapshotRequestEpoch();
      setAttachmentsByComment((current) => ({
        ...current,
        [commentId]: loadingPanel<Attachment>(),
      }));
      apiRequest<Attachment[]>(
        `/tickets/${ticketId}/comments/${commentId}/attachments`,
      )
        .then((items) => {
          if (isCurrentEpoch(epoch)) {
            setAttachmentsByComment((current) => ({
              ...current,
              [commentId]: loadedPanel(items),
            }));
          }
        })
        .catch((caught) => {
          if (isCurrentEpoch(epoch)) {
            setAttachmentsByComment((current) => ({
              ...current,
              [commentId]: failedPanel<Attachment>(toErrorMessage(caught)),
            }));
          }
        });
    },
    [isCurrentEpoch, snapshotRequestEpoch, ticketId],
  );

  const loadCustomer = useCallback(async () => {
    const epoch = snapshotRequestEpoch();
    setCustomerLoading(true);
    setCustomerError("");
    try {
      const summary = await apiRequest<TicketCustomerSummary>(`/tickets/${ticketId}/customer`);
      if (isCurrentEpoch(epoch)) setCustomer(summary);
    } catch (caught) {
      if (isCurrentEpoch(epoch)) setCustomerError(toErrorMessage(caught));
    } finally {
      if (isCurrentEpoch(epoch)) setCustomerLoading(false);
    }
  }, [isCurrentEpoch, snapshotRequestEpoch, ticketId]);

  useEffect(() => {
    if (activeTab === "customer") void loadCustomer();
  }, [activeTab, loadCustomer]);

  const loadRelated = useCallback(async () => {
    const epoch = snapshotRequestEpoch();
    setRelatedLoading(true);
    setRelatedError("");
    try {
      const items = await apiRequest<RelatedTicket[]>(`/tickets/${ticketId}/related`);
      if (isCurrentEpoch(epoch)) setRelated(items);
    } catch (caught) {
      if (isCurrentEpoch(epoch)) setRelatedError(toErrorMessage(caught));
    } finally {
      if (isCurrentEpoch(epoch)) setRelatedLoading(false);
    }
  }, [isCurrentEpoch, snapshotRequestEpoch, ticketId]);

  useEffect(() => {
    if (activeTab === "related") void loadRelated();
  }, [activeTab, loadRelated]);

  const searchCandidates = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void loadCandidates(ticket.department_id, candidateSearch, false, snapshotRequestEpoch());
  };

  const loadMoreCandidates = () => {
    void loadCandidates(ticket.department_id, candidateSearch, true, snapshotRequestEpoch());
  };

  const searchRelated = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!relatedSearch.trim()) {
      setRelatedCandidates([]);
      return;
    }
    try {
      const found = await apiRequest<Ticket[]>(
        `/tickets/?search=${encodeURIComponent(relatedSearch.trim())}&limit=10&sort_by=updated_at&sort_order=desc`,
      );
      setRelatedCandidates(found.filter((candidate) => candidate.id !== ticketId));
    } catch (caught) {
      setRelatedError(toErrorMessage(caught));
    }
  };

  const addRelated = async (candidateId: string) => {
    setRelatedBusy(candidateId);
    setRelatedError("");
    try {
      await apiRequest(`/tickets/${ticketId}/related`, {
        method: "POST",
        body: { related_ticket_id: candidateId },
      });
      setRelatedCandidates((items) => items.filter((item) => item.id !== candidateId));
      await loadRelated();
    } catch (caught) {
      setRelatedError(toErrorMessage(caught));
    } finally {
      setRelatedBusy("");
    }
  };

  const removeRelated = async (candidateId: string) => {
    setRelatedBusy(candidateId);
    setRelatedError("");
    try {
      await apiRequest(`/tickets/${ticketId}/related/${candidateId}`, { method: "DELETE" });
      setRelated((items) => items.filter((item) => item.ticket_id !== candidateId));
    } catch (caught) {
      setRelatedError(toErrorMessage(caught));
    } finally {
      setRelatedBusy("");
    }
  };

  const activeAnalysis = analyses.find(
    (item) => item.status === "pending" || item.status === "running",
  );
  const activeAnalysisId = activeAnalysis?.id;

  useEffect(() => {
    if (!activeAnalysisId) {
      setAnalysisPolling(false);
      setAnalysisPollError("");
      return;
    }
    let cancelled = false;
    let attempt = 0;
    let timer: number | undefined;

    const schedule = (delay: number) => {
      timer = window.setTimeout(poll, delay);
    };
    const poll = async () => {
      if (cancelled) return;
      setAnalysisPolling(true);
      try {
        const updated = await apiRequest<AnalysisResult>(
          `/analysis-results/${activeAnalysisId}`,
        );
        if (cancelled) return;
        attempt = 0;
        setAnalysisPollError("");
        setAnalyses((items) =>
          items.map((item) => (item.id === updated.id ? updated : item)),
        );
        if (updated.status === "pending" || updated.status === "running") {
          schedule(2000);
        } else {
          setAnalysisPolling(false);
        }
      } catch (caught) {
        if (cancelled) return;
        if (
          caught instanceof ApiError &&
          (caught.status === 401 || caught.status === 403)
        ) {
          // Signed out or lost permission: stop quietly.
          setAnalysisPolling(false);
          return;
        }
        attempt += 1;
        if (attempt > MAX_POLL_RETRIES) {
          setAnalysisPolling(false);
          setAnalysisPollError(
            "Live analysis updates stopped after repeated failures. Reload the ticket to retry.",
          );
          return;
        }
        setAnalysisPollError(`Reconnecting to analysis status… (retry ${attempt})`);
        schedule(Math.min(15000, 2000 * 2 ** (attempt - 1)));
      }
    };
    schedule(2000);
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [activeAnalysisId, ticketId]);

  // Announce a terminal analysis state once, and only for an attempt requested
  // in this session. Polling re-updates the same record; the watched set makes
  // the message idempotent and prevents a previous ticket's result from leaking.
  useEffect(() => {
    for (const item of analyses) {
      if (!watchedAnalyses.current.has(item.id)) continue;
      if (item.status === "completed") {
        watchedAnalyses.current.delete(item.id);
        notify("Analysis completed.");
      } else if (item.status === "failed") {
        watchedAnalyses.current.delete(item.id);
        notify("Analysis failed. Review the error and retry.");
      }
    }
  }, [analyses, notify]);

  const perform = async (label: string, action: () => Promise<unknown>) => {
    setBusy(label);
    setMutationError("");
    setMutationConflict(false);
    try {
      await action();
      await load();
      notify(`${label} completed.`);
    } catch (caught) {
      setMutationError(toErrorMessage(caught));
      if (caught instanceof ApiError && caught.status === 409) {
        setMutationConflict(true);
      }
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
          <button className="button secondary" onClick={() => void load(true)}>
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
  const userNameById = new Map(
    [...userMap.values()].map((item) => [
      item.id,
      `${item.first_name} ${item.last_name}`.trim() || item.nickname,
    ]),
  );
  const assignedAgent = ticket.assigned_agent_id
    ? userMap.get(ticket.assigned_agent_id)
    : undefined;
  const canClaim = isAgent && ticket.status === "New" && !ticket.assigned_agent_id;
  const canStart =
    isAgent &&
    ticket.status === "Open" &&
    ticket.assigned_agent_id === identity?.userId;
  const canAnalyze =
    isManager || (isAgent && ticket.assigned_agent_id === identity?.userId);
  const canConfigureRouting =
    isManager && ticket.status === "New" && !ticket.assigned_agent_id;
  const canComment = computeCanComment(ticket, role, identity?.userId);
  const transitions = allowedTransitions(ticket, role, identity?.userId);
  const latestAnalysis = analyses[0];

  const submitReply = async (
    body: string,
    visibility: Visibility,
    files: File[],
  ): Promise<File[]> => {
    setMutationError("");
    try {
      const created = await apiRequest<Comment>(`/tickets/${ticket.id}/comments`, {
        method: "POST",
        body: { body: body.trim(), visibility },
      });
      // The comment is committed. Drop the committed text from the draft now,
      // before the refresh, so a remount can never restore it as unsent work.
      clearDraft(ticket.id);
      const failed: File[] = [];
      for (const file of files) {
        const form = new FormData();
        form.append("file", file);
        try {
          await apiRequest(`/tickets/${ticket.id}/comments/${created.id}/attachments`, {
            method: "POST",
            body: form,
          });
        } catch {
          failed.push(file);
        }
      }
      if (failed.length > 0) {
        // Keep only the failed uploads, tied to the comment that was saved.
        saveDraft(ticket.id, { body: "", visibility, files: failed });
      }
      await load();
      notify("Reply posted.");
      return failed;
    } catch (caught) {
      setMutationError(toErrorMessage(caught));
      throw caught;
    }
  };

  const runAnalysis = async () => {
    setBusy("Analysis");
    setMutationError("");
    try {
      const result = await apiRequest<AnalysisResult>(
        `/tickets/${ticket.id}/analysis-results`,
        { method: "POST" },
      );
      watchedAnalyses.current.add(result.id);
      setAnalyses((items) => [
        result,
        ...items.filter((item) => item.id !== result.id),
      ]);
      // HTTP 202 means the request was accepted, not that analysis finished.
      notify(result.status === "running" ? "Analysis running." : "Analysis queued.");
    } catch (caught) {
      setMutationError(toErrorMessage(caught));
    } finally {
      setBusy("");
    }
  };

  const downloadAttachment = async (attachment: Attachment) => {
    setDownloadingAttachment(attachment.id);
    try {
      const blob = await downloadFile(
        `/tickets/${ticket.id}/comments/${attachment.comment_id}/attachments/${attachment.id}`,
      );
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = attachment.original_filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setMutationError(toErrorMessage(caught));
    } finally {
      setDownloadingAttachment("");
    }
  };

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
          {mutationConflict && (
            <>
              {" "}
              The ticket changed on the server. Reload it before retrying; this
              action was not replayed automatically.
              <button className="button secondary compact" onClick={() => void load()}>
                Reload ticket
              </button>
            </>
          )}
        </div>
      )}

      <div className="detail-grid">
        <div className="detail-main">
          <section className="card description-card">
            <h2>Description</h2>
            <p>{ticket.description}</p>
          </section>

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
            {isManager && (
              <div className="assignment-picker">
                <strong>Assign to agent</strong>
                {!ticket.department_id ? (
                  <p className="muted">
                    Route the ticket to a department before assigning an agent.
                  </p>
                ) : (
                  <>
                    <form className="candidate-search" onSubmit={searchCandidates}>
                      <label>
                        Search eligible agents
                        <input
                          value={candidateSearch}
                          onChange={(event) => setCandidateSearch(event.target.value)}
                          placeholder="Name, nickname, or email"
                        />
                      </label>
                      <button className="button subtle">Search</button>
                    </form>
                    {candidatesError ? (
                      <p className="field-error" role="alert">
                        {candidatesError}{" "}
                        <button
                          type="button"
                          className="button subtle"
                          onClick={loadMoreCandidates}
                        >
                          Try again
                        </button>
                      </p>
                    ) : candidatesLoading && candidates.length === 0 ? (
                      <p className="muted">Loading eligible agents…</p>
                    ) : candidates.length === 0 ? (
                      <p className="muted">
                        No live agent in this department is available right now.
                      </p>
                    ) : (
                      <>
                        <div className="inline-action">
                          <select
                            aria-label="Assign to agent"
                            value={selectedAgent}
                            onChange={(event) => setSelectedAgent(event.target.value)}
                          >
                            {candidates.map((agent) => (
                              <option key={agent.user_id} value={agent.user_id}>
                                {agent.first_name} {agent.last_name} (
                                {agent.current_active_tickets}/{agent.max_active_tickets}
                                {agent.current_active_tickets >= agent.max_active_tickets
                                  ? " · at capacity"
                                  : ""}
                                )
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
                        {candidatesHasMore && (
                          <button
                            className="button subtle"
                            disabled={candidatesLoading}
                            onClick={loadMoreCandidates}
                          >
                            {candidatesLoading ? "Loading agents…" : "Load more agents"}
                          </button>
                        )}
                      </>
                    )}
                  </>
                )}
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


          {canAnalyze && (
            <AnalysisCard
              result={latestAnalysis}
              busy={busy === "Analysis"}
              polling={analysisPolling}
              pollError={analysisPollError}
              onRun={() => void runAnalysis()}
            />
          )}

          <section className="card tabs-card">
            <div className="tab-row">
              <button className={activeTab === "activity" ? "active" : undefined} onClick={() => setActiveTab("activity")}>
                Activity
              </button>
              <button className={activeTab === "customer" ? "active" : undefined} onClick={() => setActiveTab("customer")}>
                Customer Info
              </button>
              <button className={activeTab === "related" ? "active" : undefined} onClick={() => setActiveTab("related")}>
                Related Issues
              </button>
            </div>
            {activeTab === "activity" ? (
              <>
                <div className="comment-list">
                  {comments.length === 0 ? (
                    <p className="muted">No comments yet.</p>
                  ) : (
                    comments.map((comment) => {
                      const author = userMap.get(comment.author_user_id);
                      const authorName =
                        comment.author_display_name ||
                        (author
                          ? `${author.first_name} ${author.last_name}`
                          : `User ${comment.author_user_id.slice(0, 8)}`);
                      return (
                        <article
                          key={comment.id}
                          className={`comment comment-${comment.visibility.toLowerCase().replaceAll(" ", "-")}`}
                        >
                          <div className="avatar small">
                            {author
                              ? initials(author.first_name, author.last_name)
                              : authorName.slice(0, 2).toUpperCase()}
                          </div>
                          <div>
                            <header>
                              <strong>{authorName}</strong>
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
                            <AttachmentList
                              state={attachmentsByComment[comment.id]}
                              downloadingId={downloadingAttachment}
                              onDownload={(attachment) => void downloadAttachment(attachment)}
                              onRetry={() => retryAttachment(comment.id)}
                            />
                          </div>
                        </article>
                      );
                    })
                  )}
                </div>
                {commentsHasMore && (
                  <button
                    className="button secondary"
                    disabled={commentsLoadingMore}
                    onClick={() => void loadOlderComments()}
                  >
                    {commentsLoadingMore ? "Loading earlier comments…" : "Load earlier comments"}
                  </button>
                )}
                {canComment && (
                  <ReplyComposer
                    key={ticket.id}
                    ticketId={ticket.id}
                    isCustomer={isCustomer}
                    isManager={isManager}
                    onSubmit={submitReply}
                  />
                )}
              </>
            ) : activeTab === "customer" ? (
              customerLoading ? (
                <StatePanel kind="loading" title="Loading customer info" message="Requesting the ticket-scoped customer summary…" />
              ) : customerError ? (
                <StatePanel
                  kind="error"
                  title="Customer info unavailable"
                  message={customerError}
                  action={<button className="button secondary" onClick={() => void loadCustomer()}>Try again</button>}
                />
              ) : customer ? (
                <dl className="customer-summary">
                  <div><dt>Name</dt><dd>{customer.display_name}</dd></div>
                  <div><dt>Nickname</dt><dd>{customer.nickname}</dd></div>
                  <div><dt>Account status</dt><dd>{customer.account_status}</dd></div>
                  <div><dt>Email</dt><dd>{customer.email || "Not available"}</dd></div>
                  <div><dt>Phone</dt><dd>{customer.phone || "Not available"}</dd></div>
                </dl>
              ) : (
                <p className="muted">No customer summary is available.</p>
              )
            ) : relatedLoading ? (
              <StatePanel kind="loading" title="Loading related issues" message="Checking visible ticket links…" />
            ) : relatedError ? (
              <StatePanel
                kind="error"
                title="Related issues unavailable"
                message={relatedError}
                action={<button className="button secondary" onClick={() => void loadRelated()}>Try again</button>}
              />
            ) : (
              <div className="related-panel">
                {related.length === 0 ? <p className="muted">No related tickets yet.</p> : (
                  <ul className="related-list">
                    {related.map((item) => (
                      <li key={item.link_id}>
                        <div>
                          <Link className="ticket-link" to={`/tickets/${item.ticket_id}`}>
                            #{item.ticket_id.slice(0, 8)} · {item.title}
                          </Link>
                          <span>{item.status} · {priorityLabel(item.priority)}</span>
                        </div>
                        {isManager && (
                          <button
                            className="button subtle"
                            disabled={Boolean(relatedBusy)}
                            onClick={() => void removeRelated(item.ticket_id)}
                          >
                            {relatedBusy === item.ticket_id ? "Removing…" : "Unlink"}
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
                {isManager && (
                  <form className="related-search" onSubmit={(event) => void searchRelated(event)}>
                    <label>
                      Find a visible ticket to link
                      <input value={relatedSearch} onChange={(event) => setRelatedSearch(event.target.value)} placeholder="ID, title, or description" />
                    </label>
                    <button className="button secondary">Search</button>
                  </form>
                )}
                {relatedCandidates.length > 0 && (
                  <ul className="related-list candidates">
                    {relatedCandidates.map((candidate) => (
                      <li key={candidate.id}>
                        <div><strong>#{candidate.id.slice(0, 8)} · {candidate.title}</strong><span>{candidate.status} · {priorityLabel(candidate.priority)}</span></div>
                        <button className="button secondary" disabled={Boolean(relatedBusy)} onClick={() => void addRelated(candidate.id)}>
                          {relatedBusy === candidate.id ? "Linking…" : "Link"}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </section>

          <section className="card history-card">
            <h2>Activity timeline</h2>
            {history.length === 0 ? (
              <p className="muted">No visible history events.</p>
            ) : (
              <>
                <ol>
                  {history.map((event) => (
                    <li key={event.id}>
                      <i />
                      <div>
                        <strong>{formatHistoryEvent(event, userNameById)}</strong>
                        <span>{historyActor(event)} · {formatDate(event.created_at)}</span>
                      </div>
                    </li>
                  ))}
                </ol>
                {historyHasMore && (
                  <button
                    className="button secondary"
                    disabled={historyLoadingMore}
                    onClick={() => void loadMoreHistory()}
                  >
                    {historyLoadingMore ? "Loading newer activity…" : "Load newer activity"}
                  </button>
                )}
              </>
            )}
          </section>
        </div>

        <aside className="detail-side">
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
                  {ticket.assigned_agent_name
                    ? ticket.assigned_agent_name
                    : assignedAgent
                      ? `${assignedAgent.first_name} ${assignedAgent.last_name}`
                      : ticket.assigned_agent_id
                        ? ticket.assigned_agent_id.slice(0, 8)
                        : "Unassigned"}
                </dd>
              </div>
              <div>
                <dt>Category</dt>
                <dd>{categoryLabel(ticket.category)}</dd>
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

export function computeCanComment(
  ticket: Ticket,
  role: Role | undefined,
  userId: string | undefined,
): boolean {
  const isManager = Boolean(role && MANAGER_ROLES.includes(role));
  const isAgent = role === "agent";
  const isReadonly = role === "agent_readonly";
  const isCustomer = role === "user";
  return (
    !isReadonly &&
    (isManager ||
      (isAgent &&
        (ticket.assigned_agent_id === userId ||
          (ticket.status === "New" && !ticket.assigned_agent_id))) ||
      (isCustomer && ticket.creator_user_id === userId))
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
  polling = false,
  pollError,
  onRun,
}: {
  result?: AnalysisResult;
  busy: boolean;
  polling?: boolean;
  pollError?: string;
  onRun: () => void;
}) {
  const live = result?.status === "pending" || result?.status === "running";
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
          <strong>Analysis queued</strong>
          <p>Waiting for analysis to start.</p>
        </div>
      ) : result.status === "running" ? (
        <div className="analysis-body">
          <span className="running-label">
            <i /> Analyzing ticket…
          </span>
          <div className="progress">
            <span />
          </div>
          <p>This page checks for updates automatically; you can safely navigate away.</p>
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
      {pollError && live && (
        <p className="muted small" role="status">
          <AlertTriangle size={13} /> {pollError}
        </p>
      )}
      {polling && live && !pollError && (
        <p className="muted small" role="status">
          Checking for analysis updates…
        </p>
      )}
    </section>
  );
}

const ALLOWED_ATTACHMENTS = new Set([
  "application/pdf",
  "image/png",
  "image/jpeg",
  "text/plain",
  "text/csv",
  "application/json",
]);
const MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024;
const MAX_ATTACHMENTS = 5;

export function ReplyComposer({
  ticketId,
  isCustomer,
  isManager,
  onSubmit,
}: {
  ticketId: string;
  isCustomer: boolean;
  isManager: boolean;
  onSubmit: (body: string, visibility: Visibility, files: File[]) => Promise<File[]>;
}) {
  const { getDraft, saveDraft, clearDraft } = useDrafts();
  const initial = getDraft(ticketId);
  const [body, setBody] = useState(initial?.body ?? "");
  const [visibility, setVisibility] = useState<Visibility>(initial?.visibility ?? "Public");
  const [files, setFiles] = useState<File[]>(initial?.files ?? []);
  const [fileError, setFileError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const hasDraft = body.trim().length > 0 || files.length > 0;

  // Persist only meaningful input. An untouched empty composer is not a draft,
  // so it never warns on reload or leaks onto another ticket.
  useEffect(() => {
    if (hasDraft) saveDraft(ticketId, { body, visibility, files });
    else clearDraft(ticketId);
  }, [body, visibility, files, hasDraft, ticketId, saveDraft, clearDraft]);

  const selectFiles = (fileList: FileList | null) => {
    if (!fileList) return;
    const incoming = Array.from(fileList);
    const invalid = incoming.find(
      (file) => !ALLOWED_ATTACHMENTS.has(file.type) || file.size > MAX_ATTACHMENT_BYTES,
    );
    if (invalid) {
      setFileError(`${invalid.name} is not an allowed type or is larger than 5 MiB.`);
      return;
    }
    if (files.length + incoming.length > MAX_ATTACHMENTS) {
      setFileError("A comment can have at most 5 attachments.");
      return;
    }
    setFileError("");
    setFiles((current) => [...current, ...incoming]);
  };

  const discard = () => {
    clearDraft(ticketId);
    setBody("");
    setVisibility("Public");
    setFiles([]);
    setFileError("");
  };

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!body.trim() || submitting) return;
    setSubmitting(true);
    setFileError("");
    try {
      const failed = await onSubmit(body, visibility, files);
      setBody("");
      if (failed.length > 0) {
        setFileError(`Comment saved, but ${failed.length} attachment(s) failed. Retry them.`);
      }
      setFiles(failed);
    } catch {
      // Preserve the text and selected files so the reply can be retried.
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="reply-form" onSubmit={(event) => void submit(event)}>
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
        {hasDraft && (
          <button type="button" className="button subtle" onClick={discard}>
            Discard draft
          </button>
        )}
      </div>
      <textarea
        rows={4}
        value={body}
        onChange={(event) => setBody(event.target.value)}
        placeholder="Write a reply…"
      />
      {hasDraft && <p className="muted small">Unsent draft saved for this ticket.</p>}
      {fileError && <p className="field-error" role="alert">{fileError}</p>}
      {files.length > 0 && (
        <ul className="selected-files">
          {files.map((file, index) => (
            <li key={`${file.name}-${index}`}>
              <span>{file.name} · {Math.max(1, Math.round(file.size / 1024))} KB</span>
              <button type="button" onClick={() => setFiles((items) => items.filter((_, itemIndex) => itemIndex !== index))}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <footer>
        <input
          ref={fileInputRef}
          className="visually-hidden"
          type="file"
          multiple
          accept=".pdf,.png,.jpg,.jpeg,.txt,.csv,.json"
          onChange={(event) => {
            selectFiles(event.target.files);
            event.target.value = "";
          }}
        />
        <button
          type="button"
          className="icon-button"
          aria-label="Attach a file"
          onClick={() => fileInputRef.current?.click()}
        >
          <Paperclip size={17} />
        </button>
        <button className="button primary" disabled={!body.trim() || submitting}>
          {submitting ? "Submitting…" : "Submit reply"}
        </button>
      </footer>
    </form>
  );
}
