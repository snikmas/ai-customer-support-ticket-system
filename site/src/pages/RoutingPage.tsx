import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { apiRequest, toErrorMessage } from "../api/client";
import type { RoutingCatalog } from "../api/types";
import { StatePanel } from "../components/StatePanel";
import { useToast } from "../components/ToastContext";

type CatalogKind = "departments" | "skills";

function CatalogSection({ kind, items, onRefresh }: { kind: CatalogKind; items: RoutingCatalog[]; onRefresh: () => void }) {
  const { notify } = useToast();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const endpoint = `/${kind}/`;

  const create = async (event: FormEvent) => {
    event.preventDefault();
    setBusy("create"); setError("");
    try {
      await apiRequest(endpoint, { method: "POST", body: { name: name.trim(), description: description.trim() || null } });
      setName(""); setDescription(""); onRefresh(); notify(`${kind === "departments" ? "Department" : "Skill"} created.`);
    } catch (caught) { setError(toErrorMessage(caught)); } finally { setBusy(""); }
  };

  const update = async (item: RoutingCatalog, body: { name?: string; description?: string | null }) => {
    setBusy(item.id); setError("");
    try { await apiRequest(`${endpoint}${item.id}`, { method: "PATCH", body }); onRefresh(); notify("Routing catalog updated."); }
    catch (caught) { setError(toErrorMessage(caught)); } finally { setBusy(""); }
  };

  const archive = async (item: RoutingCatalog) => {
    setBusy(item.id); setError("");
    try { await apiRequest(`${endpoint}${item.id}`, { method: "DELETE" }); onRefresh(); notify("Routing catalog archived."); }
    catch (caught) { setError(toErrorMessage(caught)); } finally { setBusy(""); }
  };

  return <section className="card routing-section">
    <header><div><p className="eyebrow">Catalog</p><h2>{kind === "departments" ? "Departments" : "Skills"}</h2></div><span>{items.filter((item) => !item.deleted_at).length} active · {items.filter((item) => item.deleted_at).length} archived</span></header>
    {error && <div className="alert error" role="alert">{error}</div>}
    <form className="routing-create" onSubmit={create}><label>Name<input value={name} onChange={(event) => setName(event.target.value)} required /></label><label>Description<input value={description} onChange={(event) => setDescription(event.target.value)} /></label><button className="button primary" disabled={!name.trim() || busy === "create"}>{busy === "create" ? "Creating…" : "Create"}</button></form>
    <div className="routing-list">{items.map((item) => <div className={`routing-row ${item.deleted_at ? "archived" : ""}`} key={item.id}>
      <div><strong>{item.name}</strong><span>{item.description || "No description"}</span>{item.deleted_at && <em>Archived</em>}</div>
      {!item.deleted_at && <div className="inline-action"><button className="button subtle" disabled={Boolean(busy)} onClick={() => void update(item, { name: window.prompt("New name", item.name) || item.name })}>Rename</button><button className="button subtle danger" disabled={Boolean(busy)} onClick={() => void archive(item)}>Archive</button></div>}
    </div>)}</div>
  </section>;
}

export function RoutingPage() {
  const [departments, setDepartments] = useState<RoutingCatalog[]>([]);
  const [skills, setSkills] = useState<RoutingCatalog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const [departmentData, skillData] = await Promise.all([apiRequest<RoutingCatalog[]>("/departments/?include_archived=true"), apiRequest<RoutingCatalog[]>("/skills/?include_archived=true")]); setDepartments(departmentData); setSkills(skillData); }
    catch (caught) { setError(toErrorMessage(caught)); } finally { setLoading(false); }
  }, []);
  useEffect(() => void load(), [load]);
  if (loading) return <StatePanel kind="loading" title="Loading routing" message="Requesting departments and skills…" />;
  if (error) return <StatePanel kind="error" title="Routing unavailable" message={error} action={<button className="button secondary" onClick={() => void load()}>Try again</button>} />;
  return <><div className="page-heading"><div><p className="eyebrow">Administration</p><h1>Routing</h1><p>Configure active departments and skills. Archived records stay visible here and cannot be selected for new routing.</p></div></div><div className="routing-grid"><CatalogSection kind="departments" items={departments} onRefresh={() => void load()} /><CatalogSection kind="skills" items={skills} onRefresh={() => void load()} /></div></>;
}
