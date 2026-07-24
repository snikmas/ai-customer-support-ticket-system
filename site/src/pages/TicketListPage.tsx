import { AlertTriangle, ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { apiRequest, toErrorMessage } from "../api/client";
import {
  PRIORITY_LABELS,
  TICKET_STATUSES,
  type Priority,
  type RoutingCatalog,
  type Ticket,
  type TicketStatus,
} from "../api/types";
import { StatePanel } from "../components/StatePanel";
import { formatDate, priorityLabel, relativeTime } from "../lib/format";

const PAGE_SIZE = 20;

export function TicketListPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [departments, setDepartments] = useState<RoutingCatalog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const page = Number(searchParams.get("page") || "1");
  const status = (searchParams.get("status") || "") as TicketStatus | "";
  const priority = searchParams.get("priority") as `${Priority}` | null;
  const overdue = searchParams.get("overdue") === "true";
  const sortBy = searchParams.get("sort_by") || "created_at";
  const sortOrder = searchParams.get("sort_order") || "desc";

  const updateParam = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setSearchParams(next);
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    const query = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String((page - 1) * PAGE_SIZE),
      sort_by: sortBy,
      sort_order: sortOrder,
    });
    if (status) query.set("status", status);
    if (priority) query.set("priority", priority);
    if (overdue) query.set("overdue", "true");
    try {
      const [ticketData, departmentData] = await Promise.all([
        apiRequest<Ticket[]>(`/tickets/?${query}`),
        apiRequest<RoutingCatalog[]>("/departments/"),
      ]);
      setTickets(ticketData);
      setDepartments(departmentData);
    } catch (caught) {
      setError(toErrorMessage(caught));
    } finally {
      setLoading(false);
    }
  }, [page, priority, sortBy, sortOrder, status, overdue]);

  useEffect(() => void load(), [load]);

  const departmentsById = useMemo(
    () => Object.fromEntries(departments.map((item) => [item.id, item.name])),
    [departments],
  );

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Ticket workspace</p>
          <h1>All tickets</h1>
          <p>Showing up to {PAGE_SIZE} tickets from the real API.</p>
        </div>
        <button className="button secondary" onClick={() => void load()}>
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      <section className="filter-bar" aria-label="Ticket filters">
        <label>
          Status
          <select value={status} onChange={(event) => updateParam("status", event.target.value)}>
            <option value="">All</option>
            {TICKET_STATUSES.map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          Priority
          <select
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
            value={overdue ? "true" : ""}
            onChange={(event) => updateParam("overdue", event.target.value)}
          >
            <option value="">Any</option>
            <option value="true">Overdue</option>
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
          {sortOrder === "desc" ? "Newest first" : "Oldest first"}
        </button>
      </section>

      {loading ? (
        <StatePanel kind="loading" title="Loading tickets" message="Requesting the current page from FastAPI…" />
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
      ) : tickets.length === 0 ? (
        <StatePanel
          kind="empty"
          title="No tickets found"
          message="There are no tickets matching these filters on this page."
        />
      ) : (
        <div className="table-card">
          <div className="ticket-table-wrap">
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
                  <tr key={ticket.id} onClick={() => navigate(`/tickets/${ticket.id}`)}>
                    <td>
                      <span className="ticket-id">#{ticket.id.slice(0, 8)}</span>
                      <strong>{ticket.title}</strong>
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
                      {ticket.assigned_agent_id ? ticket.assigned_agent_id.slice(0, 8) : "Unassigned"}
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
                disabled={tickets.length < PAGE_SIZE}
                onClick={() => updateParam("page", String(page + 1))}
              >
                <ChevronRight size={17} />
              </button>
            </div>
          </footer>
        </div>
      )}
    </>
  );
}
