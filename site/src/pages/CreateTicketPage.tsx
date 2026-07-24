import { AlertCircle, ChevronLeft } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { apiRequest, toErrorMessage } from "../api/client";
import {
  CATEGORIES,
  TAGS,
  type Category,
  type Tag,
  type Ticket,
} from "../api/types";

export function CreateTicketPage() {
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState<Category>("API_Error");
  const [tags, setTags] = useState<Tag[]>([]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (!title.trim() || !description.trim()) {
      setError("Title, description, and category are required.");
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
        },
      });
      navigate(`/tickets/${ticket.id}`);
    } catch (caught) {
      setError(toErrorMessage(caught));
    } finally {
      setSubmitting(false);
    }
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
          <p>
            Priority and routing are assigned after submission by the support
            system or authorized staff.
          </p>
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
        <label className="full">
          Category <span className="required">*</span>
          <select value={category} onChange={(event) => setCategory(event.target.value as Category)}>
            {CATEGORIES.map((value) => (
              <option key={value} value={value}>
                {value.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </label>
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
          <button className="button primary" disabled={submitting}>
            {submitting ? "Creating…" : "Create ticket"}
          </button>
        </footer>
      </form>
    </div>
  );
}
