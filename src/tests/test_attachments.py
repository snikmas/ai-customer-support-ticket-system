from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src import constants
from src.db import models as db_models
from src.exceptions.domain import AttachmentValidationError
from src.services import attachments
from src.services import comments as comments_service
from src.services import tickets as tickets_service
from src.storage import LocalAttachmentStorage


class FakeUpload:
    def __init__(self, filename, content_type, content):
        self.filename = filename
        self.content_type = content_type
        self.content = content

    async def read(self, limit):
        return self.content[:limit]


def test_local_storage_rejects_path_traversal(tmp_path):
    store = LocalAttachmentStorage(tmp_path)

    with pytest.raises(ValueError):
        store.path("../outside.txt")


@pytest.mark.anyio
async def test_upload_uses_generated_key_and_received_size(monkeypatch, make_user):
    requester = make_user(id="agent-1", role=constants.Role.AGENT)
    ticket = SimpleNamespace(id="ticket-1", deleted_at=None)
    comment = SimpleNamespace(id="comment-1", deleted_at=None)
    saved = {}
    now = datetime.now(timezone.utc)

    monkeypatch.setattr(tickets_service, "get_ticket", lambda *_: ticket)
    monkeypatch.setattr(comments_service, "get_comment", lambda *_: comment)
    monkeypatch.setattr(attachments.operations, "count_comment_attachments", lambda *_: 0)
    monkeypatch.setattr(
        attachments.storage,
        "save",
        lambda key, content: saved.update(key=key, content=content),
    )
    monkeypatch.setattr(
        attachments.operations,
        "create_attachment",
        lambda attachment, event: attachment,
    )

    result = await attachments.upload_attachment(
        ticket.id,
        comment.id,
        FakeUpload("../notes.txt", "text/plain", b"hello"),
        requester,
    )

    assert result.original_filename == "notes.txt"
    assert result.size_bytes == 5
    assert saved["content"] == b"hello"
    assert saved["key"].endswith(".txt")
    assert saved["key"] != "notes.txt"


@pytest.mark.anyio
async def test_upload_rejects_disallowed_type_before_persistence(monkeypatch, make_user):
    requester = make_user(id="agent-1", role=constants.Role.AGENT)
    monkeypatch.setattr(tickets_service, "get_ticket", lambda *_: SimpleNamespace(deleted_at=None))
    monkeypatch.setattr(comments_service, "get_comment", lambda *_: SimpleNamespace(deleted_at=None))
    monkeypatch.setattr(attachments.operations, "count_comment_attachments", lambda *_: 0)

    with pytest.raises(AttachmentValidationError) as exc_info:
        await attachments.upload_attachment(
            "ticket-1",
            "comment-1",
            FakeUpload("payload.exe", "application/octet-stream", b"not allowed"),
            requester,
        )

    assert exc_info.value.code == "attachment_type_not_allowed"
