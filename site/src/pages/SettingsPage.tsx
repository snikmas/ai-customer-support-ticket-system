import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { ApiError, apiRequest, toErrorMessage } from "../api/client";
import type { AgentProfile, RoutingCatalog, User } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { StatePanel } from "../components/StatePanel";
import { useToast } from "../components/ToastContext";
import { agentReadiness } from "../lib/agents";

export function SettingsPage() {
  const { user, refreshUser, logout } = useAuth();
  const { notify } = useToast();
  const [profile, setProfile] = useState<User | null>(user);
  const [agentProfile, setAgentProfile] = useState<AgentProfile | null>(null);
  const [departments, setDepartments] = useState<RoutingCatalog[]>([]);
  const [skills, setSkills] = useState<RoutingCatalog[]>([]);
  const [firstName, setFirstName] = useState(user?.first_name || "");
  const [lastName, setLastName] = useState(user?.last_name || "");
  const [nickname, setNickname] = useState(user?.nickname || "");
  const [email, setEmail] = useState(user?.email || "");
  const [phone, setPhone] = useState(user?.phone || "");
  const [password, setPassword] = useState("");
  const [availability, setAvailability] = useState<AgentProfile["availability_status"]>("offline");
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);

  useEffect(() => {
    if (!user) return;
    setProfile(user); setFirstName(user.first_name); setLastName(user.last_name); setNickname(user.nickname); setEmail(user.email); setPhone(user.phone);
    if (user.role === "agent") {
      apiRequest<AgentProfile>(`/users/${user.id}/agent-profile`).then((value) => { setAgentProfile(value); setAvailability(value.availability_status); setReason(value.availability_reason || ""); setNote(value.availability_note || ""); }).catch(() => setAgentProfile(null));
      Promise.all([
        apiRequest<RoutingCatalog[]>("/departments/"),
        apiRequest<RoutingCatalog[]>("/skills/"),
      ]).then(([departmentList, skillList]) => { setDepartments(departmentList); setSkills(skillList); }).catch(() => undefined);
    }
  }, [user]);

  const saveProfile = async (event: FormEvent) => {
    event.preventDefault(); if (!user) return; setBusy("profile"); setError(""); setConflict(false);
    try {
      const updated = await apiRequest<User>(`/users/${user.id}`, { method: "PATCH", body: { first_name: firstName, last_name: lastName, nickname, email, phone } });
      setProfile(updated);
      await refreshUser();
      notify("Profile settings saved.");
    } catch (caught) {
      setError(toErrorMessage(caught));
      setConflict(caught instanceof ApiError && caught.status === 409);
    } finally { setBusy(""); }
  };

  const savePassword = async (event: FormEvent) => {
    event.preventDefault(); if (!user || !password) return; setBusy("password"); setError("");
    try {
      await apiRequest(`/users/${user.id}`, { method: "PATCH", body: { password } });
      setPassword("");
      notify("Password changed. Signing you out of this session.");
      // A password change revokes every refresh session, so the client must
      // sign out instead of trying to renew the old session.
      await logout().catch(() => undefined);
    } catch (caught) {
      setError(toErrorMessage(caught));
      setBusy("");
    }
  };

  const saveAvailability = async (event: FormEvent) => {
    event.preventDefault(); if (!user) return; setBusy("availability"); setError("");
    try { const updated = await apiRequest<AgentProfile>(`/users/${user.id}/availability`, { method: "PATCH", body: { availability_status: availability, reason: reason || null, note: note || null } }); setAgentProfile(updated); notify(availability === "available" ? "Available status saved; waiting-ticket reconciliation may run." : "Availability saved."); }
    catch (caught) { setError(toErrorMessage(caught)); } finally { setBusy(""); }
  };

  if (!profile) return <StatePanel kind="loading" title="Loading settings" message="Restoring your profile…" />;
  const readiness = profile.role === "agent" ? agentReadiness(agentProfile) : null;
  const departmentName = agentProfile?.department_id ? departments.find((item) => item.id === agentProfile.department_id)?.name || "Unknown department" : "None";
  const skillNames = (agentProfile?.skill_ids ?? []).map((id) => skills.find((item) => item.id === id)?.name || "Unknown skill");

  return <><div className="page-heading"><div><p className="eyebrow">Personal workspace</p><h1>My Settings</h1><p>Update safe profile fields separately from your password and operational availability.</p></div></div>
    {readiness && !readiness.canReceive && <div className="alert warning" role="status">{readiness.setupIssue ? <><strong>Routing profile incomplete.</strong> {readiness.setupIssue} A manager must finish the routing setup.</> : <><strong>{readiness.detail}.</strong> You will receive work again after completing active tickets.</>}</div>}
    {error && <div className="alert error" role="alert">{error}{conflict && <button className="button secondary compact" onClick={() => void refreshUser()}>Reload profile</button>}</div>}
    <div className="settings-grid">
    <form className="card settings-card" onSubmit={saveProfile}><h2>Profile</h2><label>Nickname<input value={nickname} onChange={(event) => setNickname(event.target.value)} required /></label><label>First name<input value={firstName} onChange={(event) => setFirstName(event.target.value)} required /></label><label>Last name<input value={lastName} onChange={(event) => setLastName(event.target.value)} required /></label><label>Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label><label>Phone<input value={phone} onChange={(event) => setPhone(event.target.value)} required /></label><button className="button primary" disabled={busy === "profile"}>{busy === "profile" ? "Saving…" : "Save profile"}</button></form>
    <form className="card settings-card" onSubmit={savePassword}><h2>Change password</h2><p className="muted">Your current password is never displayed or returned by the API. Changing it signs you out of this session.</p><label>New password<input type="password" minLength={15} value={password} onChange={(event) => setPassword(event.target.value)} required /></label><button className="button secondary" disabled={busy === "password"}>{busy === "password" ? "Changing…" : "Change password"}</button></form>
    {profile.role === "agent" && <form className="card settings-card" onSubmit={saveAvailability}><h2>Agent availability</h2><p className="muted">Available agents can receive waiting tickets when routing reconciliation runs.</p><label>Status<select value={availability} onChange={(event) => setAvailability(event.target.value as AgentProfile["availability_status"])}><option value="available">Available</option><option value="paused">Paused</option><option value="offline">Offline</option></select></label><label>Reason<select value={reason} onChange={(event) => setReason(event.target.value)}><option value="">No reason</option><option value="BREAK">Break</option><option value="MEETING">Meeting</option><option value="TRAINING">Training</option><option value="OTHER_WORK">Other work</option><option value="SHIFT_ENDED">Shift ended</option><option value="PERSONAL_LEAVE">Personal leave</option><option value="OTHER">Other</option></select></label><label>Note<textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={200} /></label><button className="button primary" disabled={busy === "availability"}>{busy === "availability" ? "Saving…" : "Save availability"}</button></form>}
    {profile.role === "agent" && <section className="card settings-card"><h2>Routing profile</h2><p className="muted">Department, skills, and capacity are managed by a manager or administrator.</p><dl className="customer-summary"><div><dt>Department</dt><dd>{departmentName}</dd></div><div><dt>Skills</dt><dd>{skillNames.length > 0 ? skillNames.join(", ") : "None"}</dd></div><div><dt>Capacity</dt><dd>{agentProfile ? `${agentProfile.current_active_tickets}/${agentProfile.max_active_tickets}` : "—"}</dd></div></dl></section>}
  </div></>;
}
