"""Phase F regression tests: attachment limits, races, cleanup, and event loop.

The behavior asserted here is the desired post-repair behavior. The pre-fix
diagnostic probes (which asserted the defect) are intentionally not part of this
suite.
"""

import asyncio
import io
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from main import app
from src import constants, models
from src.db import models as db_models, operations
from src.exceptions.domain import (
    AttachmentNotFoundError,
    AttachmentValidationError,
    AuthorizationError,
    InternalOperationError,
)
from src.routers import tickets as tickets_router
from src.services import attachments, comments
from src.storage import LocalAttachmentStorage
from src.tests.test_department_skill_routing import _catalog, _profile, _ticket, _user


def _seed(engine):
    now = constants.utc_now()
    with Session(engine) as session, session.begin():
        session.add(_catalog(db_models.Department, "support", now))
        session.add_all(
            [
                _user("customer", constants.Role.USER, now),
                _user("manager", constants.Role.MANAGER, now),
            ]
        )
        session.flush()
        session.add(_ticket("ticket", now, "support", []))


def _make_comment() -> db_models.Comment:
    return comments.create_ticket_comment(
        "ticket",
        models.CommentCreate(body="files", visibility=constants.Visibility.PUBLIC),
        operations.get_user("customer"),
    )


def _upload_file(content: bytes = b"demo") -> UploadFile:
    return UploadFile(filename="test.txt", file=io.BytesIO(content))


def _attempt_upload(comment_id: str, requester) -> str:
    try:
        asyncio.run(
            attachments.upload_attachment(
                "ticket", comment_id, _upload_file(), requester
            )
        )
        return "ok"
    except AttachmentValidationError as exc:
        return exc.code


# ---------------------------------------------------------------------------
# Count cap under concurrency (SQLite and PostgreSQL)
# ---------------------------------------------------------------------------
def test_concurrent_uploads_at_cap_produce_at_most_five(
    mutation_engine, tmp_path, monkeypatch
):
    engine = mutation_engine
    monkeypatch.setattr(
        attachments, "storage", LocalAttachmentStorage(tmp_path / "uploads")
    )
    _seed(engine)
    comment = _make_comment()
    requester = operations.get_user("customer")

    for _ in range(attachments.MAX_ATTACHMENTS_PER_COMMENT - 1):
        asyncio.run(
            attachments.upload_attachment(
                "ticket", comment.id, _upload_file(), requester
            )
        )
    assert operations.count_comment_attachments(comment.id) == 4

    barrier = Barrier(2)

    def race(_):
        barrier.wait(timeout=20)
        return _attempt_upload(comment.id, requester)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(race, range(2)))

    assert sorted(outcomes) == ["attachment_count_exceeded", "ok"], outcomes

    db_count = operations.count_comment_attachments(comment.id)
    assert db_count == attachments.MAX_ATTACHMENTS_PER_COMMENT
    listed = operations.get_comment_attachments(comment.id)
    assert len(listed) == db_count
    assert operations.get_comment(comment.id).attachments_count == db_count


# ---------------------------------------------------------------------------
# Upload racing deletion / visibility restriction
# ---------------------------------------------------------------------------
def test_upload_racing_comment_deletion_commits_nothing(
    mutation_engine, tmp_path, monkeypatch
):
    engine = mutation_engine
    storage = LocalAttachmentStorage(tmp_path / "uploads")
    monkeypatch.setattr(attachments, "storage", storage)
    _seed(engine)
    comment = _make_comment()
    requester = operations.get_user("customer")

    real_save = storage.save

    def save_then_delete(key, content):
        real_save(key, content)
        # Simulates the deletion committing after the service's initial read but
        # before the metadata transaction begins.
        comments.delete_comment("ticket", comment.id, requester)

    monkeypatch.setattr(storage, "save", save_then_delete)

    with pytest.raises(AttachmentNotFoundError):
        asyncio.run(
            attachments.upload_attachment(
                "ticket", comment.id, _upload_file(), requester
            )
        )

    assert operations.count_comment_attachments(comment.id) == 0
    assert operations.get_comment(comment.id).deleted_at is not None
    assert storage.generated_keys() == []


def test_upload_racing_visibility_restriction_commits_nothing(
    mutation_engine, tmp_path, monkeypatch
):
    engine = mutation_engine
    storage = LocalAttachmentStorage(tmp_path / "uploads")
    monkeypatch.setattr(attachments, "storage", storage)
    _seed(engine)
    comment = _make_comment()
    requester = operations.get_user("customer")
    manager = operations.get_user("manager")

    real_save = storage.save

    def save_then_restrict(key, content):
        real_save(key, content)
        comments.update_comment(
            "ticket",
            comment.id,
            models.CommentUpdate(
                visibility=constants.Visibility.PRIVATE_TO_MANAGER
            ),
            manager,
        )

    monkeypatch.setattr(storage, "save", save_then_restrict)

    with pytest.raises(AuthorizationError):
        asyncio.run(
            attachments.upload_attachment(
                "ticket", comment.id, _upload_file(), requester
            )
        )

    assert operations.count_comment_attachments(comment.id) == 0
    assert storage.generated_keys() == []


def test_upload_racing_reassignment_commits_nothing(
    mutation_engine, tmp_path, monkeypatch
):
    engine = mutation_engine
    storage = LocalAttachmentStorage(tmp_path / "uploads")
    monkeypatch.setattr(attachments, "storage", storage)
    _seed(engine)
    now = constants.utc_now()
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                _user("agent", constants.Role.AGENT, now),
                _user("agent2", constants.Role.AGENT, now),
            ]
        )
        session.flush()
        session.add(_profile("agent", "support", now, []))
        session.add(_profile("agent2", "support", now, []))
    operations.update_ticket("ticket", {"assigned_agent_id": "agent"})

    comment = comments.create_ticket_comment(
        "ticket",
        models.CommentCreate(
            body="agent files", visibility=constants.Visibility.INTERNAL
        ),
        operations.get_user("agent"),
    )
    requester = operations.get_user("agent")

    real_save = storage.save

    def save_then_reassign(key, content):
        real_save(key, content)
        # The ticket is reassigned after the upload's initial authorization but
        # before its metadata transaction commits.
        operations.update_ticket("ticket", {"assigned_agent_id": "agent2"})

    monkeypatch.setattr(storage, "save", save_then_reassign)

    with pytest.raises(AuthorizationError):
        asyncio.run(
            attachments.upload_attachment(
                "ticket", comment.id, _upload_file(), requester
            )
        )

    assert operations.count_comment_attachments(comment.id) == 0
    assert storage.generated_keys() == []
    assert operations.get_comment(comment.id).attachments_count == 0


# ---------------------------------------------------------------------------
# API route and failure cleanup (SQLite only, real route + database)
# ---------------------------------------------------------------------------
@pytest.fixture
def api_engine(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'attachments-api.db'}",
        connect_args={"timeout": 10},
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    db_models.Base.metadata.create_all(engine)
    monkeypatch.setattr(operations, "engine", engine)
    monkeypatch.setattr(
        attachments, "storage", LocalAttachmentStorage(tmp_path / "uploads")
    )
    _seed(engine)
    yield engine
    app.dependency_overrides.clear()
    engine.dispose()


def _client_as(user_id: str) -> TestClient:
    app.dependency_overrides[tickets_router.get_current_user] = (
        lambda: operations.get_user(user_id)
    )
    return TestClient(app)


def _route(comment_id: str) -> str:
    return f"/tickets/ticket/comments/{comment_id}/attachments"


def test_oversized_upload_rejected_through_direct_api_route(api_engine):
    comment = _make_comment()
    client = _client_as("customer")
    oversized = b"x" * (attachments.MAX_ATTACHMENT_SIZE + 1)

    response = client.post(
        _route(comment.id),
        files={"file": ("big.txt", oversized, "text/plain")},
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "attachment_size_exceeded"
    assert operations.count_comment_attachments(comment.id) == 0
    assert attachments.storage.generated_keys() == []


def test_storage_write_failure_leaves_no_metadata_or_blob(api_engine, monkeypatch):
    comment = _make_comment()
    requester = operations.get_user("customer")
    storage = attachments.storage

    def failing_save(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(storage, "save", failing_save)

    with pytest.raises(InternalOperationError) as exc_info:
        asyncio.run(
            attachments.upload_attachment(
                "ticket", comment.id, _upload_file(), requester
            )
        )
    assert exc_info.value.code == "attachment_save_failed"
    assert operations.count_comment_attachments(comment.id) == 0
    assert storage.generated_keys() == []


def test_metadata_failure_removes_unreferenced_blob(api_engine, monkeypatch):
    comment = _make_comment()
    requester = operations.get_user("customer")
    storage = attachments.storage

    def failing_commit(*_args, **_kwargs):
        raise RuntimeError("metadata unavailable")

    monkeypatch.setattr(operations, "create_attachment_guarded", failing_commit)

    with pytest.raises(InternalOperationError) as exc_info:
        asyncio.run(
            attachments.upload_attachment(
                "ticket", comment.id, _upload_file(), requester
            )
        )
    assert exc_info.value.code == "attachment_save_failed"
    assert operations.count_comment_attachments(comment.id) == 0
    assert storage.generated_keys() == []


# ---------------------------------------------------------------------------
# Blocking storage must not stall the async event loop
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_slow_storage_does_not_block_event_loop(api_engine, monkeypatch):
    comment = _make_comment()
    requester = operations.get_user("customer")
    order = []
    real_save = attachments.storage.save

    def slow_save(key, content):
        time.sleep(0.25)
        order.append("storage")
        real_save(key, content)

    monkeypatch.setattr(attachments.storage, "save", slow_save)

    async def other_work():
        await asyncio.sleep(0.02)
        order.append("other")

    await asyncio.gather(
        attachments.upload_attachment(
            "ticket", comment.id, _upload_file(), requester
        ),
        other_work(),
    )

    assert order.index("other") < order.index("storage")
