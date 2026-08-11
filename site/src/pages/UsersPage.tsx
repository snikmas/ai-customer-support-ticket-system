import { RefreshCw, Search } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { apiRequest, toErrorMessage } from "../api/client";
import { STAFF_ROLES, type Role, type User } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { StatePanel } from "../components/StatePanel";
import { useToast } from "../components/ToastContext";

const PAGE_SIZE = 20;

export function UsersPage() {
  const { user } = useAuth();
  const { notify } = useToast();
  const [params, setParams] = useSearchParams();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [staff, setStaff] = useState({ nickname: "", first_name: "", last_name: "", email: "", phone: "+", password: "", role: "agent" as Role });

  const page = Number(params.get("page") || "1");
  const search = params.get("search") || "";
  const role = params.get("role") || "";
  const status = params.get("user_status") || "";

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    const query = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String((page - 1) * PAGE_SIZE),
      sort_by: "first_name",
      sort_order: "asc",
    });
    if (search) query.set("search", search);
    if (role) query.set("role", role);
    if (status) query.set("user_status", status);
    try {
      const listed = await apiRequest<User[]>(`/users/?${query}`);
      const withProfiles = await Promise.all(
        listed.map(async (item) => {
          if (item.role !== "agent") return item;
          try {
            return { ...item, agent_profile: await apiRequest<User["agent_profile"]>(`/users/${item.id}/agent-profile`) };
          } catch {
            return item;
          }
        }),
      );
      setUsers(withProfiles);
    } catch (caught) {
      setError(toErrorMessage(caught));
    } finally {
      setLoading(false);
    }
  }, [page, role, search, status]);

  useEffect(() => void load(), [load]);

  const updateParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next);
  };

  const updateUser = async (id: string, body: Partial<Pick<User, "role" | "user_status">>) => {
    setBusy(id);
    try {
      await apiRequest<User>(`/users/${id}`, { method: "PATCH", body });
      await load();
      notify("User updated.");
    } catch (caught) {
      setError(toErrorMessage(caught));
    } finally {
      setBusy("");
    }
  };

  const createStaff = async (event: FormEvent) => {
    event.preventDefault(); setBusy("create"); setError("");
    try { await apiRequest<User>("/users/staff", { method: "POST", body: { ...staff, max_active_tickets: 5 } }); setStaff({ nickname: "", first_name: "", last_name: "", email: "", phone: "+", password: "", role: "agent" }); setCreateOpen(false); await load(); notify("Staff account created."); }
    catch (caught) { setError(toErrorMessage(caught)); } finally { setBusy(""); }
  };

  if (loading) return <StatePanel kind="loading" title="Loading users" message="Requesting the staff directory…" />;
  if (error) return <StatePanel kind="error" title="Users unavailable" message={error} action={<button className="button secondary" onClick={() => void load()}>Try again</button>} />;

  const canEdit = user?.role === "admin" || user?.role === "super_admin";
  return (
    <>
      <div className="page-heading">
        <div><p className="eyebrow">Administration</p><h1>Users</h1><p>Role-aware directory with agent capacity and availability.</p></div>
        <button className="button secondary" onClick={() => void load()}><RefreshCw size={16} /> Refresh</button>
      </div>
      {canEdit && <section className="card staff-create-card">
        <button className="button secondary" onClick={() => setCreateOpen((value) => !value)}>{createOpen ? "Cancel staff creation" : "Create staff account"}</button>
        {createOpen && <form className="staff-create-form" onSubmit={createStaff}>
          <label>Nickname<input required value={staff.nickname} onChange={(event) => setStaff({ ...staff, nickname: event.target.value })} /></label>
          <label>First name<input required value={staff.first_name} onChange={(event) => setStaff({ ...staff, first_name: event.target.value })} /></label>
          <label>Last name<input required value={staff.last_name} onChange={(event) => setStaff({ ...staff, last_name: event.target.value })} /></label>
          <label>Email<input required type="email" value={staff.email} onChange={(event) => setStaff({ ...staff, email: event.target.value })} /></label>
          <label>Phone<input required value={staff.phone} onChange={(event) => setStaff({ ...staff, phone: event.target.value })} /></label>
          <label>Temporary password<input required minLength={15} type="password" value={staff.password} onChange={(event) => setStaff({ ...staff, password: event.target.value })} /></label>
          <label>Role<select value={staff.role} onChange={(event) => setStaff({ ...staff, role: event.target.value as Role })}>{STAFF_ROLES.filter((value) => value !== "agent_readonly").map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
          <button className="button primary" disabled={busy === "create"}>{busy === "create" ? "Creating…" : "Create staff"}</button>
        </form>}
      </section>}
      <section className="filter-bar" aria-label="User filters">
        <label className="search-filter">Search<input aria-label="Search users" value={search} onChange={(event) => updateParam("search", event.target.value)} placeholder="Name, email, or ID" /></label>
        <label>Role<select value={role} onChange={(event) => updateParam("role", event.target.value)}><option value="">All roles</option>{STAFF_ROLES.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
        <label>Status<select value={status} onChange={(event) => updateParam("user_status", event.target.value)}><option value="">All statuses</option><option value="Active">Active</option><option value="Banned">Banned</option><option value="Deleted">Deleted</option></select></label>
      </section>
      {users.length === 0 ? <StatePanel kind="empty" title="No users found" message="Try clearing a role, status, or search filter." /> : (
        <div className="table-card ticket-table-wrap">
          <table className="ticket-table"><thead><tr><th>User</th><th>Role</th><th>Status</th><th>Availability</th><th>Workload</th><th>Capacity</th>{canEdit && <th>Manage</th>}</tr></thead>
            <tbody>{users.map((item) => { const profile = item.agent_profile; return <tr key={item.id}>
              <td><strong>{item.first_name} {item.last_name}</strong><span className="table-subline">@{item.nickname} · {item.email}</span></td>
              <td>{canEdit ? <select aria-label={`Role for ${item.nickname}`} value={item.role} disabled={busy === item.id || item.role === "super_admin" && user?.role !== "super_admin"} onChange={(event) => void updateUser(item.id, { role: event.target.value as Role })}>{STAFF_ROLES.concat(["user"]).map((value) => <option key={value} value={value}>{value}</option>)}</select> : item.role}</td>
              <td>{canEdit ? <select aria-label={`Status for ${item.nickname}`} value={item.user_status} disabled={busy === item.id} onChange={(event) => void updateUser(item.id, { user_status: event.target.value as User["user_status"] })}><option>Active</option><option>Banned</option><option>Deleted</option></select> : item.user_status}</td>
              <td>{profile?.availability_status || "—"}</td><td>{profile ? profile.current_active_tickets : "—"}</td><td>{profile ? profile.max_active_tickets : "—"}</td>
              {canEdit && <td>{busy === item.id ? "Saving…" : profile?.can_receive_new_tickets ? "Eligible" : ""}</td>}
            </tr>; })}</tbody>
          </table>
        </div>
      )}
    </>
  );
}
