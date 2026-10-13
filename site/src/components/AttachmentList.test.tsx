import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Attachment } from "../api/types";
import { AttachmentList, failedPanel, loadedPanel, loadingPanel } from "./AttachmentList";

const attachment: Attachment = {
  id: "a-1",
  comment_id: "c-1",
  original_filename: "evidence.pdf",
  content_type: "application/pdf",
  size_bytes: 2048,
  created_at: "2026-01-01T00:00:00Z",
};

describe("AttachmentList optional-panel states", () => {
  it("shows a loading state instead of an empty result", () => {
    render(
      <AttachmentList
        state={loadingPanel<Attachment>()}
        downloadingId=""
        onDownload={vi.fn()}
        onRetry={vi.fn()}
      />,
    );

    expect(screen.getByText(/loading attachments/i)).toBeInTheDocument();
  });

  it("renders a failed lookup as an error with a scoped retry, never as zero attachments", async () => {
    const onRetry = vi.fn();
    render(
      <AttachmentList
        state={failedPanel<Attachment>("Network error")}
        downloadingId=""
        onDownload={vi.fn()}
        onRetry={onRetry}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(/could not be loaded/i);
    expect(screen.queryByText(/no attachments/i)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("renders nothing for a genuinely empty result", () => {
    const { container } = render(
      <AttachmentList
        state={loadedPanel<Attachment>([])}
        downloadingId=""
        onDownload={vi.fn()}
        onRetry={vi.fn()}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("renders downloadable attachments when loaded", () => {
    render(
      <AttachmentList
        state={loadedPanel([attachment])}
        downloadingId=""
        onDownload={vi.fn()}
        onRetry={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: /evidence\.pdf/i })).toBeInTheDocument();
  });
});
