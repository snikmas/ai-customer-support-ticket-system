import { LoaderCircle } from "lucide-react";
import type { Attachment } from "../api/types";

export interface PanelState<T> {
  status: "loading" | "loaded" | "empty" | "error";
  items: T[];
  error?: string;
}

export function loadingPanel<T>(): PanelState<T> {
  return { status: "loading", items: [] };
}

export function loadedPanel<T>(items: T[]): PanelState<T> {
  return { status: items.length > 0 ? "loaded" : "empty", items };
}

export function failedPanel<T>(error: string): PanelState<T> {
  return { status: "error", items: [], error };
}

/**
 * Render one optional attachment lookup separately from "no attachments".
 *
 * A failed request must never look like zero attachments, so this component
 * keeps loading, empty, loaded, and failed visually distinct and offers a
 * scoped retry that does not reload the whole ticket.
 */
export function AttachmentList({
  state,
  downloadingId,
  onDownload,
  onRetry,
}: {
  state: PanelState<Attachment> | undefined;
  downloadingId: string;
  onDownload: (attachment: Attachment) => void;
  onRetry: () => void;
}) {
  if (!state || state.status === "loading") {
    return (
      <p className="muted small">
        <LoaderCircle className="spin" size={13} /> Loading attachments…
      </p>
    );
  }
  if (state.status === "error") {
    return (
      <p className="field-error" role="alert">
        Attachments could not be loaded.{" "}
        <button type="button" className="button subtle" onClick={onRetry}>
          Retry
        </button>
      </p>
    );
  }
  if (state.status === "empty") {
    return null;
  }
  return (
    <ul className="comment-attachments">
      {state.items.map((attachment) => (
        <li key={attachment.id}>
          <button
            type="button"
            onClick={() => onDownload(attachment)}
            disabled={downloadingId === attachment.id}
          >
            {downloadingId === attachment.id ? "Downloading…" : attachment.original_filename}
          </button>
          <span>{Math.max(1, Math.round(attachment.size_bytes / 1024))} KB</span>
        </li>
      ))}
    </ul>
  );
}
