import { AlertCircle, ChevronLeft } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { apiRequest, toErrorMessage } from "../api/client";
import {
  CATEGORIES,
  TAGS,
  type Category,
  type RoutingCatalog,
  type Tag,
  type Ticket,
} from "../api/types";
import { StatePanel } from "../components/StatePanel";

export function CreateTicketPage() {
  const navigate = useNavigate();
  const [departments, setDepartments] = useState<RoutingCatalog[]>([]);
  const [skills, setSkills] = useState<RoutingCatalog[]>([]);
  const [catalogError, setCatalogError] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState<Category>("API_Error");
  const [departmentId, setDepartmentId] = useState("");
  const [skillIds, setSkillIds] = useState<string[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);

  useEffect(() => {
    Promise.all([
      apiRequest<RoutingCatalog[]>("/departments/"),
      apiRequest<RoutingCatalog[]>("/skills/"),
    ])
      .then(([departmentData, skillData]) => {
        setDepartments(departmentData);
        setSkills(skillData);
        setDepartmentId(departmentData[0]?.id ?? "");
      })
      .catch((caught) => setCatalogError(toErrorMessage(caught)))
      .finally(() => setLoading(false));
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (!title.trim() || !description.trim() || !departmentId) {
      setError("Title, description, category, and department are required.");
      return;
    }
    setSubmitting(true);
    try {
      const ticket = await apiRequest<Ticket>("/tickets/", {
        method: "POST",
        body: {
          title: title.trim(),
          description: description.trim(),
          category,
          tags,
          department_id: departmentId,
          skill_ids: skillIds,
        },
      });
      navigate(`/tickets/${ticket.id}`);
    } catch (caught) {
      setError(toErrorMessage(caught));
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return <StatePanel kind="loading" title="Loading ticket form" message="Loading departments and skills…" />;
  }
  if (catalogError) {
    return (
      <StatePanel
        kind="error"
        title="Ticket form is unavailable"
        message={`Routing catalogs could not be loaded. ${catalogError}`}
      />
    );
  }

  return (
    <div className="form-page">
      <button className="back-link" onClick={() => navigate("/tickets")}>
        <ChevronLeft size={17} /> Back to tickets
      </button>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Customer request</p>
          <h1>New ticket</h1>
          <p>Priority is assigned by the server and can be changed later during staff triage.</p>
        </div>
      </div>
      <form className="form-card" onSubmit={submit}>
        {error && (
          <div className="alert error" role="alert">
            <AlertCircle size={17} /> {error}
          </div>
        )}
        <label className="full">
          Title <span className="required">*</span>
          <input
            value={title}
            maxLength={200}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Brief description of the issue"
          />
        </label>
        <label className="full">
          Description <span className="required">*</span>
          <textarea
            rows={7}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Steps to reproduce, error messages, and expected versus actual behavior"
          />
        </label>
        <label>
          Category <span className="required">*</span>
          <select value={category} onChange={(event) => setCategory(event.target.value as Category)}>
            {CATEGORIES.map((value) => (
              <option key={value} value={value}>
                {value.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </label>
        <label>
          Department <span className="required">*</span>
          <select value={departmentId} onChange={(event) => setDepartmentId(event.target.value)}>
            {departments.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <fieldset className="full choice-field">
          <legend>Required skills</legend>
          <div className="choice-grid">
            {skills.map((skill) => (
              <label key={skill.id}>
                <input
                  type="checkbox"
                  checked={skillIds.includes(skill.id)}
                  onChange={(event) =>
                    setSkillIds((current) =>
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
        <fieldset className="full choice-field">
          <legend>Tags</legend>
          <div className="choice-grid tags">
            {TAGS.map((tag) => (
              <label key={tag}>
                <input
                  type="checkbox"
                  checked={tags.includes(tag)}
                  onChange={(event) =>
                    setTags((current) =>
                      event.target.checked
                        ? [...current, tag]
                        : current.filter((value) => value !== tag),
                    )
                  }
                />
                {tag}
              </label>
            ))}
          </div>
        </fieldset>
        <footer className="form-actions full">
          <button type="button" className="button secondary" onClick={() => navigate("/tickets")}>
            Cancel
          </button>
          <button className="button primary" disabled={submitting || departments.length === 0}>
            {submitting ? "Creating…" : "Create ticket"}
          </button>
        </footer>
      </form>
    </div>
  );
}
