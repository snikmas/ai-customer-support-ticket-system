import { AlertTriangle, ChevronLeft, ChevronRight, RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { apiRequest, toErrorMessage } from "../api/client";
import {
  PRIORITY_LABELS,
  CATEGORIES,
  TAGS,
  MANAGER_ROLES,
  TICKET_STATUSES,
  type Priority,
  type RoutingCatalog,
  type Ticket,
  type TicketStatus,
  type User,
} from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { StatePanel } from "../components/StatePanel";
import { categoryLabel, formatDate, priorityLabel, relativeTime } from "../lib/format";
import { fieldIssues, validationIssues } from "../lib/validation";

const PAGE_SIZE = 20;
// One extra record is the last-page probe: the API returns this array, and the
// UI displays PAGE_SIZE of them. The spare record only tells us whether Next
// exists; offsets always advance by PAGE_SIZE.
const FETCH_SIZE = PAGE_SIZE + 1;

const FILTER_KEYS = [
  "search",
  "status",
  "priority",
  "department_id",
  "assignee_id",
  "category",
  "tag",
] as const;

function sortDirectionLabel(sortBy: string, sortOrder: string): string {
  if (sortBy === "priority") {
    return sortOrder === "desc" ? "Highest priority first" : "Lowest priority first";
  }
  // Status is ordered by its stored value, which is alphabetical, not workflow.
  if (sortBy === "status") {
    return sortOrder === "desc" ? "Status Z–A" : "Status A–Z";
  }
  return sortOrder === "desc" ? "Newest first" : "Oldest first";
}

export function TicketListPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [departments, setDepartments] = useState<RoutingCatalog[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [queryFieldErrors, setQueryFieldErrors] = useState<Record<string, string>>({});

  const page = Number(searchParams.get("page") || "1");
  const status = (searchParams.get("status") || "") as TicketStatus | "";
  const priority = searchParams.get("priority") as `${Priority}` | null;
  const search = searchParams.get("search") || "";
  const assignedToMe = searchParams.get("assigned_to_me") === "true";
  const departmentId = searchParams.get("department_id") || "";
  const assigneeId = searchParams.get("assignee_id") || "";
  const category = searchParams.get("category") || "";
  const tag = searchParams.get("tag") || "";
  const overdue = searchParams.get("overdue") === "true";
  const sortBy = searchParams.get("sort_by") || "created_at";
  const sortOrder = searchParams.get("sort_order") || "desc";
  const { user } = useAuth();

  const updateParam = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setSearchParams(next);
  };

  const resetFilters = () => {
    const next = new URLSearchParams(searchParams);
    for (const key of FILTER_KEYS) next.delete(key);
    next.delete("page");
    // A destination such as My queue or Overdue is not a filter, so it stays.
    setSearchParams(next);
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    setQueryFieldErrors({});
    const query = new URLSearchParams({
      limit: String(FETCH_SIZE),
      offset: String((page - 1) * PAGE_SIZE),
      sort_by: sortBy,
      sort_order: sortOrder,
    });
    if (status) query.set("status", status);
    if (priority) query.set("priority", priority);
    if (overdue) query.set("overdue", "true");
    if (search) query.set("search", search);
    if (assignedToMe) query.set("assigned_to_me", "true");
    if (departmentId) query.set("department_id", departmentId);
    if (assigneeId) query.set("assignee_id", assigneeId);
    if (category) query.set("category", category);
    if (tag) query.set("tag", tag);
    try {
      const requests: [Promise<Ticket[]>, Promise<RoutingCatalog[]>, Promise<User[]>?] = [
        apiRequest<Ticket[]>(`/tickets/?${query}`),
        apiRequest<RoutingCatalog[]>("/departments/"),
      ];
      if (user && MANAGER_ROLES.includes(user.role)) {
        requests.push(apiRequest<User[]>("/users/?limit=100&sort_by=first_name&sort_order=asc"));
      }
      const [ticketData, departmentData, userData] = await Promise.all(requests);
      setTickets(ticketData.slice(0, PAGE_SIZE));
      setHasMore(ticketData.length > PAGE_SIZE);
      setDepartments(departmentData);
      setUsers(userData || []);
    } catch (caught) {
      setError(toErrorMessage(caught));
      setQueryFieldErrors(fieldIssues(validationIssues(caught), "query"));
    } finally {
      setLoading(false);
    }
  }, [assignedToMe, assigneeId, category, departmentId, overdue, page, priority, search, sortBy, sortOrder, status, tag, user]);

  useEffect(() => void load(), [load]);

  const departmentsById = useMemo(
    () => Object.fromEntries(departments.map((item) => [item.id, item.name])),
    [departments],
  );

  const filterErrorSummary = Object.values(queryFieldErrors).join(" ");
  const invalid = (field: string) => (queryFieldErrors[field] ? true : undefined);
  const anyFilter = Boolean(
    search || status || priority || overdue || departmentId || assigneeId || category || tag,
  );

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Ticket workspace</p>
          <h1>{assignedToMe ? "My queue" : "All tickets"}</h1>
          <p>Showing up to {PAGE_SIZE} tickets.</p>
        </div>
        <button className="button secondary" onClick={() => void load()}>
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      <section className="filter-bar" aria-label="Ticket filters">
        <label className="search-filter">
          Search
          <input
            aria-label="Search ticket text"
            aria-invalid={invalid("search")}
            value={search}
            onChange={(event) => updateParam("search", event.target.value)}
            placeholder="ID, title, or description"
          />
        </label>
        <label>
          Status
          <select
            aria-invalid={invalid("status")}
            value={status}
            onChange={(event) => updateParam("status", event.target.value)}
          >
            <option value="">All</option>
            {TICKET_STATUSES.map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          Priority
          <select
            aria-invalid={invalid("priority")}
            value={priority ?? ""}
            onChange={(event) => updateParam("priority", event.target.value)}
          >
            <option value="">Any</option>
            {([4, 3, 2, 1] as Priority[]).map((value) => (
              <option key={value} value={value}>
                {PRIORITY_LABELS[value]}
              </option>
            ))}
          </select>
        </label>
        <label>
          SLA
          <select
            aria-invalid={invalid("overdue")}
            value={overdue ? "true" : ""}
            onChange={(event) => updateParam("overdue", event.target.value)}
          >
            <option value="">Any</option>
            <option value="true">Overdue</option>
          </select>
        </label>
        <label>
          Department
          <select
            aria-invalid={invalid("department_id")}
            value={departmentId}
            onChange={(event) => updateParam("department_id", event.target.value)}
          >
            <option value="">Any</option>
            {departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>
        {user && MANAGER_ROLES.includes(user.role) && (
          <label>
            Assignee
            <select
              aria-invalid={invalid("assignee_id")}
              value={assigneeId}
              onChange={(event) => updateParam("assignee_id", event.target.value)}
            >
              <option value="">Anyone</option>
              {users.filter((item) => item.role === "agent").map((item) => (
                <option key={item.id} value={item.id}>{item.first_name} {item.last_name}</option>
              ))}
            </select>
          </label>
        )}
        <label>
          Category
          <select
            aria-invalid={invalid("category")}
            value={category}
            onChange={(event) => updateParam("category", event.target.value)}
          >
            <option value="">Any</option>
            {CATEGORIES.map((item) => <option key={item} value={item}>{categoryLabel(item)}</option>)}
          </select>
        </label>
        <label>
          Tag
          <select
            aria-invalid={invalid("tag")}
            value={tag}
            onChange={(event) => updateParam("tag", event.target.value)}
          >
            <option value="">Any</option>
            {TAGS.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <label>
          Sort
          <select value={sortBy} onChange={(event) => updateParam("sort_by", event.target.value)}>
            <option value="created_at">Created</option>
            <option value="updated_at">Updated</option>
            <option value="status">Status</option>
            <option value="priority">Priority</option>
          </select>
        </label>
        <button
          className="sort-direction"
          onClick={() => updateParam("sort_order", sortOrder === "desc" ? "asc" : "desc")}
        >
          {sortDirectionLabel(sortBy, sortOrder)}
        </button>
        {search && (
          <button className="sort-direction" onClick={() => updateParam("search", "")}>
            <X size={14} /> Clear search
          </button>
        )}
        {anyFilter && (
          <button className="sort-direction" onClick={resetFilters}>
            Reset filters
          </button>
        )}
      </section>

      {filterErrorSummary && (
        <p className="field-error" role="alert">
          {filterErrorSummary}
        </p>
      )}

      {loading ? (
        <StatePanel kind="loading" title="Loading tickets" message="Loading tickets…" />
      ) : error ? (
        <StatePanel
          kind="error"
          title="Tickets could not be loaded"
          message={error}
          action={
            <button className="button secondary" onClick={() => void load()}>
              Try again
            </button>
          }
        />
      ) : (
        <div className="table-card">
          {tickets.length === 0 ? (
            <StatePanel
              kind="empty"
              title={page > 1 ? "No tickets on this page" : "No tickets found"}
              message={
                page > 1
                  ? "This page has no results. Use Previous to return to the list."
                  : search
                    ? `No tickets match “${search}”. Try a different search or clear it.`
                    : "There are no tickets matching these filters."
              }
            />
          ) : (
            <>
              <div
                className="ticket-table-wrap"
                role="region"
                aria-label="Tickets table"
                tabIndex={0}
              >
                <table className="ticket-table">
                  <thead>
                    <tr>
                      <th>Ticket</th>
                      <th>Priority</th>
                      <th>Status</th>
                      <th>Department</th>
                      <th>Assignee</th>
                      <th>SLA deadline</th>
                      <th>Updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tickets.map((ticket) => (
                      <tr key={ticket.id}>
                        <td>
                          <span className="ticket-id">#{ticket.id.slice(0, 8)}</span>
                          <Link className="ticket-title-link" to={`/tickets/${ticket.id}`}>
                            {ticket.title}
                          </Link>
                        </td>
                        <td>
                          <span className={`priority priority-${ticket.priority}`}>
                            <i />
                            {priorityLabel(ticket.priority)}
                          </span>
                        </td>
                        <td>
                          <span className={`status status-${ticket.status.toLowerCase().replaceAll(" ", "-")}`}>
                            {ticket.status}
                          </span>
                        </td>
                        <td>{ticket.department_id ? departmentsById[ticket.department_id] || "Unknown" : "—"}</td>
                        <td className="mono-short">
                          {ticket.assigned_agent_name ||
                            (ticket.assigned_agent_id ? ticket.assigned_agent_id.slice(0, 8) : "Unassigned")}
                        </td>
                        <td>
                          {ticket.is_overdue ? (
                            <span className="overdue">
                              <AlertTriangle size={14} /> Overdue
                            </span>
                          ) : (
                            formatDate(ticket.due_at)
                          )}
                        </td>
                        <td title={formatDate(ticket.updated_at)}>{relativeTime(ticket.updated_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="scroll-hint">Scroll horizontally for more columns</p>
            </>
          )}
          {(tickets.length > 0 || page > 1) && (
            <footer className="pagination">
              <span>
                Page {page} · {tickets.length} result{tickets.length === 1 ? "" : "s"}
              </span>
              <div>
                <button
                  aria-label="Previous page"
                  disabled={page <= 1}
                  onClick={() => updateParam("page", String(page - 1))}
                >
                  <ChevronLeft size={17} />
                </button>
                <button
                  aria-label="Next page"
                  disabled={!hasMore}
                  onClick={() => updateParam("page", String(page + 1))}
                >
                  <ChevronRight size={17} />
                </button>
              </div>
            </footer>
          )}
        </div>
      )}
    </>
  );
}
