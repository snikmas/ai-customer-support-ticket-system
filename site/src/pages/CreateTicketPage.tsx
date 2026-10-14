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
import { categoryLabel } from "../lib/format";

const MAX_TAGS = 10;

export function CreateTicketPage() {
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState<Category>("API_Error");
  const [tags, setTags] = useState<Tag[]>([]);
  const [tagQuery, setTagQuery] = useState("");
  const [tagsOpen, setTagsOpen] = useState(false);
  const [tagError, setTagError] = useState("");

  const toggleTag = (tag: Tag, checked: boolean) => {
    setTagError("");
    if (checked) {
      if (tags.length >= MAX_TAGS) {
        setTagError(`You can add up to ${MAX_TAGS} tags.`);
        return;
      }
      setTags((current) => [...current, tag]);
    } else {
      setTags((current) => current.filter((value) => value !== tag));
    }
  };

  const availableTags = TAGS.filter((tag) => !tags.includes(tag))
    .filter((tag) => tag.includes(tagQuery.trim().toLowerCase()));

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
                {categoryLabel(value)}
              </option>
            ))}
          </select>
        </label>
        <fieldset className="full choice-field">
          <legend>Tags <span className="muted small">Optional · up to {MAX_TAGS}</span></legend>
          {tags.length > 0 && (
            <ul className="selected-tags">
              {tags.map((tag) => (
                <li key={tag}>
                  <span>{tag}</span>
                  <button
                    type="button"
                    aria-label={`Remove ${tag}`}
                    onClick={() => setTags((current) => current.filter((value) => value !== tag))}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}
          <button
            type="button"
            className="button subtle"
            aria-expanded={tagsOpen}
            onClick={() => setTagsOpen((value) => !value)}
          >
            {tagsOpen ? "Hide tags" : "Add tags"}
          </button>
          {tagsOpen && (
            <div className="tag-choices">
              <input
                type="search"
                aria-label="Search tags"
                value={tagQuery}
                onChange={(event) => setTagQuery(event.target.value)}
                placeholder="Search tags"
              />
              <div className="choice-grid tags">
                {availableTags.map((tag) => (
                  <label key={tag}>
                    <input
                      type="checkbox"
                      checked={tags.includes(tag)}
                      onChange={(event) => toggleTag(tag, event.target.checked)}
                    />
                    {tag}
                  </label>
                ))}
                {availableTags.length === 0 && <p className="muted small">No tags match.</p>}
              </div>
            </div>
          )}
          {tagError && <p className="field-error" role="alert">{tagError}</p>}
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
