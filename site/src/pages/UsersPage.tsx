import { RefreshCw, Search } from "lucide-react";
import { Fragment, useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { apiRequest, toErrorMessage } from "../api/client";
import {
  STAFF_ROLES,
  type AgentProfile,
  type Role,
  type RoutingCatalog,
  type User,
} from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { StatePanel } from "../components/StatePanel";
import { useToast } from "../components/ToastContext";
import { agentReadiness } from "../lib/agents";

const PAGE_SIZE = 20;

interface RoutingForm {
  department_id: string;
  skill_ids: string[];
  max_active_tickets: number;
}

const EMPTY_STAFF = {
  nickname: "",
  first_name: "",
  last_name: "",
  email: "",
  phone: "+",
  password: "",
  role: "agent" as Role,
  department_id: "",
  skill_ids: [] as string[],
  max_active_tickets: 5,
};

export function UsersPage() {
  const { user } = useAuth();
  const { notify } = useToast();
  const [params, setParams] = useSearchParams();
  const [users, setUsers] = useState<User[]>([]);
  const [departments, setDepartments] = useState<RoutingCatalog[]>([]);
  const [skills, setSkills] = useState<RoutingCatalog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [staff, setStaff] = useState(EMPTY_STAFF);
  const [configuring, setConfiguring] = useState("");
  const [routingForm, setRoutingForm] = useState<RoutingForm>({
    department_id: "",
    skill_ids: [],
    max_active_tickets: 5,
  });

  const page = Number(params.get("page") || "1");
  const search = params.get("search") || "";
  const role = params.get("role") || "";
  const status = params.get("user_status") || "";

  const canManage = Boolean(user && ["manager", "admin", "super_admin"].includes(user.role));
  const canAdmin = user?.role === "admin" || user?.role === "super_admin";
  const showManage = canManage;

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
            return {
              ...item,
              agent_profile: await apiRequest<User["agent_profile"]>(
                `/users/${item.id}/agent-profile`,
              ),
            };
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

  useEffect(() => {
    if (!canManage) return;
    Promise.all([
      apiRequest<RoutingCatalog[]>("/departments/"),
      apiRequest<RoutingCatalog[]>("/skills/"),
    ])
      .then(([departmentList, skillList]) => {
        setDepartments(departmentList);
        setSkills(skillList);
      })
      .catch(() => {
        setDepartments([]);
        setSkills([]);
      });
  }, [canManage]);

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
    event.preventDefault();
    setBusy("create");
    setError("");
    const isAgent = staff.role === "agent";
    const body: Record<string, unknown> = {
      nickname: staff.nickname,
      first_name: staff.first_name,
      last_name: staff.last_name,
      email: staff.email,
      phone: staff.phone,
      password: staff.password,
      role: staff.role,
      max_active_tickets: isAgent ? staff.max_active_tickets : 5,
      skill_ids: isAgent ? staff.skill_ids : [],
    };
    if (isAgent && staff.department_id) body.department_id = staff.department_id;
    try {
      await apiRequest<User>("/users/staff", { method: "POST", body });
      setStaff(EMPTY_STAFF);
      setCreateOpen(false);
      await load();
      notify(
        isAgent
          ? "Agent created. Complete the routing profile before expecting assignments."
          : "Staff account created.",
      );
    } catch (caught) {
      setError(toErrorMessage(caught));
    } finally {
      setBusy("");
    }
  };

  const openRouting = (item: User) => {
    if (configuring === item.id) {
      setConfiguring("");
      return;
    }
    const profile = item.agent_profile;
    setRoutingForm({
      department_id: profile?.department_id ?? "",
      skill_ids: profile?.skill_ids ?? [],
      max_active_tickets: profile?.max_active_tickets ?? 5,
    });
    setConfiguring(item.id);
  };

  const saveRouting = async (event: FormEvent, id: string) => {
    event.preventDefault();
    setBusy(id);
    setError("");
    const body: Record<string, unknown> = {
      max_active_tickets: routingForm.max_active_tickets,
      skill_ids: routingForm.skill_ids,
    };
    if (routingForm.department_id) body.department_id = routingForm.department_id;
    try {
      await apiRequest<AgentProfile>(`/users/${id}/agent-profile`, {
        method: "PATCH",
        body,
      });
      setConfiguring("");
      await load();
      notify("Routing profile saved.");
    } catch (caught) {
      setError(toErrorMessage(caught));
    } finally {
      setBusy("");
    }
  };

  if (loading) return <StatePanel kind="loading" title="Loading users" message="Requesting the staff directory…" />;
  if (error) return <StatePanel kind="error" title="Users unavailable" message={error} action={<button className="button secondary" onClick={() => void load()}>Try again</button>} />;

  return (
    <>
      <div className="page-heading">
        <div><p className="eyebrow">Administration</p><h1>Users</h1><p>Role-aware directory with agent capacity and availability.</p></div>
        <button className="button secondary" onClick={() => void load()}><RefreshCw size={16} /> Refresh</button>
      </div>
      {canAdmin && <section className="card staff-create-card">
        <button className="button secondary" onClick={() => setCreateOpen((value) => !value)}>{createOpen ? "Cancel staff creation" : "Create staff account"}</button>
        {createOpen && <form className="staff-create-form" onSubmit={createStaff}>
          <label>Nickname<input required value={staff.nickname} onChange={(event) => setStaff({ ...staff, nickname: event.target.value })} /></label>
          <label>First name<input required value={staff.first_name} onChange={(event) => setStaff({ ...staff, first_name: event.target.value })} /></label>
          <label>Last name<input required value={staff.last_name} onChange={(event) => setStaff({ ...staff, last_name: event.target.value })} /></label>
          <label>Email<input required type="email" value={staff.email} onChange={(event) => setStaff({ ...staff, email: event.target.value })} /></label>
          <label>Phone<input required value={staff.phone} onChange={(event) => setStaff({ ...staff, phone: event.target.value })} /></label>
          <label>Temporary password<input required minLength={15} type="password" value={staff.password} onChange={(event) => setStaff({ ...staff, password: event.target.value })} /></label>
          <label>Role<select value={staff.role} onChange={(event) => setStaff({ ...staff, role: event.target.value as Role })}>{STAFF_ROLES.filter((value) => value !== "agent_readonly").map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
          {staff.role === "agent" && (
            <>
              <label>Department<select required value={staff.department_id} onChange={(event) => setStaff({ ...staff, department_id: event.target.value })}><option value="">Select a department</option>{departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
              <label>Capacity<input type="number" min={0} max={100} value={staff.max_active_tickets} onChange={(event) => setStaff({ ...staff, max_active_tickets: Number(event.target.value) })} /></label>
              <fieldset className="skill-picker"><legend>Skills</legend>
                {skills.map((skill) => (
                  <label key={skill.id}>
                    <input type="checkbox" checked={staff.skill_ids.includes(skill.id)} onChange={(event) => setStaff({ ...staff, skill_ids: event.target.checked ? [...staff.skill_ids, skill.id] : staff.skill_ids.filter((id) => id !== skill.id) })} />
                    {skill.name}
                  </label>
                ))}
              </fieldset>
              <p className="muted small">New agents start Offline and cannot receive work until a manager sets availability to Available.</p>
            </>
          )}
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
          <table className="ticket-table"><thead><tr><th>User</th><th>Role</th><th>Status</th><th>Availability</th><th>Workload</th><th>Capacity</th><th>Routing setup</th>{showManage && <th>Manage</th>}</tr></thead>
            <tbody>{users.map((item) => {
              const profile = item.agent_profile;
              const readiness = item.role === "agent" ? agentReadiness(profile) : null;
              return (
                <Fragment key={item.id}>
                  <tr>
                    <td><strong>{item.first_name} {item.last_name}</strong><span className="table-subline">@{item.nickname} · {item.email}</span></td>
                    <td>{canAdmin ? <select aria-label={`Role for ${item.nickname}`} value={item.role} disabled={busy === item.id || item.role === "super_admin" && user?.role !== "super_admin"} onChange={(event) => void updateUser(item.id, { role: event.target.value as Role })}>{STAFF_ROLES.concat(["user"]).map((value) => <option key={value} value={value}>{value}</option>)}</select> : item.role}</td>
                    <td>{canAdmin ? <select aria-label={`Status for ${item.nickname}`} value={item.user_status} disabled={busy === item.id} onChange={(event) => void updateUser(item.id, { user_status: event.target.value as User["user_status"] })}><option>Active</option><option>Banned</option><option>Deleted</option></select> : item.user_status}</td>
                    <td>{profile?.availability_status || "—"}</td>
                    <td>{profile ? profile.current_active_tickets : "—"}</td>
                    <td>{profile ? profile.max_active_tickets : "—"}</td>
                    <td>{readiness ? <><span className={readiness.canReceive ? "badge success" : "badge warning"} title={readiness.setupIssue || readiness.detail}>{readiness.detail}</span>{readiness.setupIssue && <span className="table-subline">{readiness.setupIssue}</span>}</> : "—"}</td>
                    {showManage && <td>{item.role === "agent" ? <button className="button subtle" disabled={busy === item.id} onClick={() => openRouting(item)}>{configuring === item.id ? "Close" : "Edit routing"}</button> : busy === item.id ? "Saving…" : ""}</td>}
                  </tr>
                  {canManage && item.role === "agent" && configuring === item.id && (
                    <tr className="routing-edit-row">
                      <td colSpan={showManage ? 8 : 7}>
                        <form className="staff-create-form" onSubmit={(event) => void saveRouting(event, item.id)}>
                          <label>Department<select required value={routingForm.department_id} onChange={(event) => setRoutingForm({ ...routingForm, department_id: event.target.value })}><option value="">Select a department</option>{departments.map((dept) => <option key={dept.id} value={dept.id}>{dept.name}</option>)}</select></label>
                          <label>Capacity<input type="number" min={0} max={100} value={routingForm.max_active_tickets} onChange={(event) => setRoutingForm({ ...routingForm, max_active_tickets: Number(event.target.value) })} /></label>
                          <fieldset className="skill-picker"><legend>Skills</legend>
                            {skills.map((skill) => (
                              <label key={skill.id}>
                                <input type="checkbox" checked={routingForm.skill_ids.includes(skill.id)} onChange={(event) => setRoutingForm({ ...routingForm, skill_ids: event.target.checked ? [...routingForm.skill_ids, skill.id] : routingForm.skill_ids.filter((id) => id !== skill.id) })} />
                                {skill.name}
                              </label>
                            ))}
                          </fieldset>
                          <div className="action-buttons">
                            <button className="button primary" disabled={busy === item.id}>{busy === item.id ? "Saving…" : "Save routing"}</button>
                            <button type="button" className="button subtle" onClick={() => setConfiguring("")}>Cancel</button>
                          </div>
                        </form>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}</tbody>
          </table>
        </div>
      )}
    </>
  );
}
