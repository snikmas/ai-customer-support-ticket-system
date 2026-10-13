"""Phase B regression tests for the comment/attachment permission matrix.

Each test asserts the desired behavior after the Phase B repair. The original
diagnostic probes (asserting the broken behavior) live outside the tracked suite.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from main import app
from src import constants, models
from src.db import models as db_models, operations
from src.exceptions import (
    AlreadyDeletedError,
    AuthorizationError,
    CommentNotFoundError,
    TicketNotFoundError,
)
from src.routers import tickets as tickets_router
from src.services import attachments, comments, tickets as tickets_service
from src.storage import LocalAttachmentStorage
from src.tests.test_department_skill_routing import _catalog, _profile, _ticket, _user

PUBLIC = constants.Visibility.PUBLIC
INTERNAL = constants.Visibility.INTERNAL
PRIVATE = constants.Visibility.PRIVATE_TO_MANAGER
NOW = datetime.now(timezone.utc)


@pytest.fixture
def db(mutation_engine, tmp_path, monkeypatch):
    """Seed one support catalog on whichever engine the suite is running.

    ``mutation_engine`` provides an empty SQLite or PostgreSQL 16 database and
    points the operations layer at it, so the comment-authorization and
    write-boundary race cases execute on both engines through one fixture.
    """
    engine = mutation_engine
    monkeypatch.setattr(
        attachments,
        "storage",
        LocalAttachmentStorage(tmp_path / "uploads"),
    )
    now = constants.utc_now()
    with Session(engine) as session, session.begin():
        session.add(_catalog(db_models.Department, "support", now))
        for user_id, role in [
            ("customer", constants.Role.USER),
            ("agent", constants.Role.AGENT),
            ("agent2", constants.Role.AGENT),
            ("readonly", constants.Role.AGENT_READONLY),
            ("manager", constants.Role.MANAGER),
            ("admin", constants.Role.ADMIN),
        ]:
            session.add(_user(user_id, role, now))
        session.flush()
        session.add(_profile("agent", "support", now, []))
        session.add(_profile("agent2", "support", now, []))
        session.add(_ticket("ticket", now, "support", []))
    yield engine
    app.dependency_overrides.clear()


def client_as(user_id: str) -> TestClient:
    app.dependency_overrides[tickets_router.get_current_user] = (
        lambda: operations.get_user(user_id)
    )
    return TestClient(app)


def _comment(**overrides) -> db_models.Comment:
    values = {
        "id": "comment-1",
        "ticket_id": "ticket",
        "author_user_id": "customer",
        "body": "stored",
        "visibility": PUBLIC,
        "edited_at": None,
        "created_at": NOW,
        "updated_at": NOW,
        "deleted_at": None,
        "deleted_by_user_id": None,
        "parent_comment_id": None,
        "attachments_count": 0,
        "source": constants.Source.API,
    }
    values.update(overrides)
    return db_models.Comment(**values)


def _upload(client: TestClient, ticket_id: str, comment_id: str):
    return client.post(
        f"/tickets/{ticket_id}/comments/{comment_id}/attachments",
        files={"file": ("note.txt", b"payload", "text/plain")},
    )


# ---------------------------------------------------------------------------
# 1. Manager restricts a customer comment but cannot replace its body; the
#    customer cannot read, edit, publish, or attach to it while restricted.
# ---------------------------------------------------------------------------
def test_restricted_customer_comment_cannot_be_republished_or_hijacked(db):
    original = comments.create_ticket_comment(
        "ticket",
        models.CommentCreate(body="customer text", visibility=PUBLIC),
        operations.get_user("customer"),
    )

    moderated = comments.update_comment(
        "ticket",
        original.id,
        models.CommentUpdate(visibility=PRIVATE),
        operations.get_user("manager"),
    )
    assert moderated.visibility is PRIVATE

    for staff in ("manager", "admin"):
        with pytest.raises(AuthorizationError):
            comments.update_comment(
                "ticket",
                original.id,
                models.CommentUpdate(body="staff replacement"),
                operations.get_user(staff),
            )
        # A mixed body + permitted-visibility update is rejected as a whole.
        with pytest.raises(AuthorizationError):
            comments.update_comment(
                "ticket",
                original.id,
                models.CommentUpdate(body="staff replacement", visibility=INTERNAL),
                operations.get_user(staff),
            )

    stored = operations.get_comment(original.id)
    assert stored.body == "customer text"
    assert stored.visibility is PRIVATE

    customer = client_as("customer")
    assert customer.get(f"/tickets/ticket/comments/{original.id}").status_code == 403
    assert (
        customer.patch(
            f"/tickets/ticket/comments/{original.id}", json={"body": "mine again"}
        ).status_code
        == 403
    )
    assert (
        customer.patch(
            f"/tickets/ticket/comments/{original.id}", json={"visibility": "Public"}
        ).status_code
        == 403
    )
    assert _upload(customer, "ticket", original.id).status_code == 403
    assert operations.get_comment(original.id).body == "customer text"


# ---------------------------------------------------------------------------
# 2. Legacy data: a customer comment made private with a staff-replaced body
#    cannot be revealed by the customer. Seeded directly, not via the route.
# ---------------------------------------------------------------------------
def test_legacy_staff_edited_private_comment_stays_hidden(db):
    with Session(db) as session, session.begin():
        session.add(
            _comment(
                id="legacy",
                author_user_id="customer",
                body="staff replaced body",
                visibility=PRIVATE,
                edited_at=NOW,
            )
        )

    customer = client_as("customer")
    listed = customer.get("/tickets/ticket/comments").json()["data"]
    assert all(item["id"] != "legacy" for item in listed)
    assert customer.get("/tickets/ticket/comments/legacy").status_code == 403
    assert (
        customer.patch(
            "/tickets/ticket/comments/legacy", json={"visibility": "Public"}
        ).status_code
        == 403
    )
    assert (
        customer.patch(
            "/tickets/ticket/comments/legacy", json={"body": "mine"}
        ).status_code
        == 403
    )
    assert operations.get_comment("legacy").body == "staff replaced body"


# ---------------------------------------------------------------------------
# 3. Read-only users read the allowed subset via list and direct endpoints;
#    they cannot write anywhere, including tickets they created.
# ---------------------------------------------------------------------------
def test_readonly_reads_allowed_subset_but_never_writes(db):
    public = comments.create_ticket_comment(
        "ticket",
        models.CommentCreate(body="public reply", visibility=PUBLIC),
        operations.get_user("manager"),
    )
    internal = comments.create_ticket_comment(
        "ticket",
        models.CommentCreate(body="internal note", visibility=INTERNAL),
        operations.get_user("manager"),
    )
    private = comments.create_ticket_comment(
        "ticket",
        models.CommentCreate(body="manager secret", visibility=PRIVATE),
        operations.get_user("manager"),
    )
    customer_comment = comments.create_ticket_comment(
        "ticket",
        models.CommentCreate(body="customer text", visibility=PUBLIC),
        operations.get_user("customer"),
    )

    readonly = client_as("readonly")
    listed = readonly.get("/tickets/ticket/comments")
    assert listed.status_code == 200
    listed_ids = {item["id"] for item in listed.json()["data"]}
    assert {public.id, internal.id, customer_comment.id} <= listed_ids
    assert private.id not in listed_ids
    assert readonly.get(f"/tickets/ticket/comments/{public.id}").status_code == 200
    assert readonly.get(f"/tickets/ticket/comments/{internal.id}").status_code == 200
    assert readonly.get(f"/tickets/ticket/comments/{private.id}").status_code == 403
    assert (
        readonly.get(f"/tickets/ticket/comments/{public.id}/attachments").status_code
        == 200
    )

    # Promote the ticket creator to read-only: earlier paths used to let them
    # keep writing their own ticket.
    operations.update_user("customer", {"role": constants.Role.AGENT_READONLY})
    owner = client_as("customer")
    assert (
        owner.post(
            "/tickets/ticket/comments",
            json={"body": "readonly write", "visibility": "Internal"},
        ).status_code
        == 403
    )
    assert (
        owner.patch(
            f"/tickets/ticket/comments/{customer_comment.id}", json={"body": "edit"}
        ).status_code
        == 403
    )
    assert (
        owner.delete(
            f"/tickets/ticket/comments/{customer_comment.id}"
        ).status_code
        == 403
    )
    assert _upload(owner, "ticket", customer_comment.id).status_code == 403
    assert (
        owner.post(
            "/tickets/",
            json={
                "title": "Read only ticket",
                "description": "should be denied",
                "category": "Account Access",
                "tags": [],
            },
        ).status_code
        == 403
    )
    assert owner.delete("/tickets/ticket").status_code == 403


# ---------------------------------------------------------------------------
# 4. A customer cannot attach files to a staff comment.
# ---------------------------------------------------------------------------
def test_customer_cannot_attach_to_staff_comment(db):
    staff_comment = comments.create_ticket_comment(
        "ticket",
        models.CommentCreate(body="staff response", visibility=PUBLIC),
        operations.get_user("manager"),
    )

    response = _upload(client_as("customer"), "ticket", staff_comment.id)
    assert response.status_code == 403
    assert operations.count_comment_attachments(staff_comment.id) == 0


# ---------------------------------------------------------------------------
# 5. Managers/admins cannot edit another author's body or add files, but may
#    change visibility and soft-delete.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("staff", ["manager", "admin"])
def test_staff_moderate_but_cannot_rewrite_another_body(db, staff):
    comment = comments.create_ticket_comment(
        "ticket",
        models.CommentCreate(body="customer text", visibility=PUBLIC),
        operations.get_user("customer"),
    )

    with pytest.raises(AuthorizationError):
        comments.update_comment(
            "ticket",
            comment.id,
            models.CommentUpdate(body="staff edit"),
            operations.get_user(staff),
        )
    assert _upload(client_as(staff), "ticket", comment.id).status_code == 403

    moderated = comments.update_comment(
        "ticket",
        comment.id,
        models.CommentUpdate(visibility=INTERNAL),
        operations.get_user(staff),
    )
    assert moderated.visibility is INTERNAL
    assert operations.get_comment(comment.id).body == "customer text"

    assert comments.delete_comment(
        "ticket", comment.id, operations.get_user(staff)
    ) is True


# ---------------------------------------------------------------------------
# 6. Wrong-ticket comment/file ids do not bypass ownership checks.
# ---------------------------------------------------------------------------
def test_wrong_ticket_ids_do_not_bypass_ownership(db):
    with Session(db) as session, session.begin():
        session.add(_ticket("ticket-2", constants.utc_now(), "support", []))

    comment = comments.create_ticket_comment(
        "ticket",
        models.CommentCreate(body="owned by ticket", visibility=PUBLIC),
        operations.get_user("customer"),
    )
    customer = operations.get_user("customer")

    with pytest.raises(CommentNotFoundError):
        comments.get_comment("ticket-2", comment.id, customer)
    with pytest.raises(CommentNotFoundError):
        comments.update_comment(
            "ticket-2", comment.id, models.CommentUpdate(body="hijack"), customer
        )
    with pytest.raises(CommentNotFoundError):
        comments.delete_comment("ticket-2", comment.id, customer)
    with pytest.raises(CommentNotFoundError):
        attachments.list_attachments("ticket-2", comment.id, customer)


# ---------------------------------------------------------------------------
# 7. Deleted comments and tickets do not regain visibility or accept content.
# ---------------------------------------------------------------------------
def test_deleted_comment_and_ticket_regain_nothing(db):
    comment = comments.create_ticket_comment(
        "ticket",
        models.CommentCreate(body="customer text", visibility=PUBLIC),
        operations.get_user("customer"),
    )
    comments.delete_comment("ticket", comment.id, operations.get_user("customer"))

    customer = operations.get_user("customer")
    manager = operations.get_user("manager")
    with pytest.raises(CommentNotFoundError):
        comments.get_comment("ticket", comment.id, customer)
    with pytest.raises(CommentNotFoundError):
        comments.update_comment(
            "ticket", comment.id, models.CommentUpdate(body="revive"), customer
        )
    with pytest.raises(CommentNotFoundError):
        comments.update_comment(
            "ticket", comment.id, models.CommentUpdate(visibility=PUBLIC), manager
        )
    with pytest.raises(AlreadyDeletedError):
        comments.delete_comment("ticket", comment.id, customer)

    tickets_service.delete_ticket("ticket", customer)
    with pytest.raises(TicketNotFoundError):
        comments.create_ticket_comment(
            "ticket",
            models.CommentCreate(body="after delete", visibility=PUBLIC),
            customer,
        )


# ---------------------------------------------------------------------------
# 9. Concurrent interleaving: a customer reads a public comment, a manager then
#    restricts it, and only then does the customer's stale write reach the
#    database. The write boundary must reject it and leave the comment hidden.
# ---------------------------------------------------------------------------
def test_stale_customer_republish_is_rejected_at_write_boundary(db):
    comment = comments.create_ticket_comment(
        "ticket",
        models.CommentCreate(body="customer text", visibility=PUBLIC),
        operations.get_user("customer"),
    )

    original = operations.update_comment_with_event

    def restrict_then_write(comment_id, mutate, **kwargs):
        # The customer's request has already passed its first read. Commit the
        # manager restriction before the customer's write boundary, then let the
        # real operation run its own fresh authorization check.
        operations.update_comment_with_event = original
        try:
            comments.update_comment(
                "ticket",
                comment_id,
                models.CommentUpdate(visibility=PRIVATE),
                operations.get_user("manager"),
            )
        finally:
            operations.update_comment_with_event = restrict_then_write
        return original(comment_id, mutate, **kwargs)

    operations.update_comment_with_event = restrict_then_write
    try:
        with pytest.raises(AuthorizationError):
            comments.update_comment(
                "ticket",
                comment.id,
                models.CommentUpdate(visibility=PUBLIC),
                operations.get_user("customer"),
            )
    finally:
        operations.update_comment_with_event = original

    stored = operations.get_comment(comment.id)
    assert stored.visibility is PRIVATE
    assert stored.body == "customer text"


def test_stale_customer_body_edit_is_rejected_at_write_boundary(db):
    comment = comments.create_ticket_comment(
        "ticket",
        models.CommentCreate(body="customer text", visibility=PUBLIC),
        operations.get_user("customer"),
    )

    original = operations.update_comment_with_event

    def restrict_then_write(comment_id, mutate, **kwargs):
        operations.update_comment_with_event = original
        try:
            comments.update_comment(
                "ticket",
                comment_id,
                models.CommentUpdate(visibility=INTERNAL),
                operations.get_user("manager"),
            )
        finally:
            operations.update_comment_with_event = restrict_then_write
        return original(comment_id, mutate, **kwargs)

    operations.update_comment_with_event = restrict_then_write
    try:
        with pytest.raises(AuthorizationError):
            comments.update_comment(
                "ticket",
                comment.id,
                models.CommentUpdate(body="silently replaced"),
                operations.get_user("customer"),
            )
    finally:
        operations.update_comment_with_event = original

    stored = operations.get_comment(comment.id)
    assert stored.visibility is INTERNAL
    assert stored.body == "customer text"


# ---------------------------------------------------------------------------
# 8. Reassigning a ticket removes the previous agent's write access.
# ---------------------------------------------------------------------------
def test_reassignment_removes_previous_agent_write_access(db):
    operations.update_ticket(
        "ticket",
        {"assigned_agent_id": "agent", "status": constants.Status.OPEN},
    )
    agent = operations.get_user("agent")
    comment = comments.create_ticket_comment(
        "ticket",
        models.CommentCreate(body="agent note", visibility=INTERNAL),
        agent,
    )
    assert (
        comments.update_comment(
            "ticket", comment.id, models.CommentUpdate(body="edited"), agent
        ).body
        == "edited"
    )

    tickets_service.assign_ticket(
        "ticket", "agent2", operations.get_user("manager")
    )

    with pytest.raises(AuthorizationError):
        comments.update_comment(
            "ticket", comment.id, models.CommentUpdate(body="stale"), agent
        )
    with pytest.raises(AuthorizationError):
        comments.create_ticket_comment(
            "ticket",
            models.CommentCreate(body="stale reply", visibility=INTERNAL),
            agent,
        )
    assert _upload(client_as("agent"), "ticket", comment.id).status_code == 403


# ---------------------------------------------------------------------------
# 10. A role change committed between the request's first read and its write
#     boundary must reject the stale write. The request object still carries the
#     manager's old role claim, but the transaction re-reads the actor's current
#     row and denies the mutation without committing an audit event.
# ---------------------------------------------------------------------------
def test_role_revocation_between_read_and_write_is_rejected(db):
    comment = comments.create_ticket_comment(
        "ticket",
        models.CommentCreate(body="customer text", visibility=PUBLIC),
        operations.get_user("customer"),
    )

    # The request captured the manager identity (and its role claim) here.
    stale_manager = operations.get_user("manager")
    assert stale_manager.role is constants.Role.MANAGER

    # A concurrent lifecycle change demotes the manager to read-only before the
    # comment write reaches its transaction.
    operations.update_user("manager", {"role": constants.Role.AGENT_READONLY})

    with pytest.raises(AuthorizationError):
        comments.update_comment(
            "ticket",
            comment.id,
            models.CommentUpdate(visibility=INTERNAL),
            stale_manager,
        )
    with pytest.raises(AuthorizationError):
        comments.update_comment(
            "ticket",
            comment.id,
            models.CommentUpdate(body="stale rewrite"),
            stale_manager,
        )

    stored = operations.get_comment(comment.id)
    assert stored.visibility is PUBLIC
    assert stored.body == "customer text"
    with Session(db) as session:
        committed_updates = session.scalar(
            select(func.count(db_models.Event.id)).where(
                db_models.Event.entity_id == comment.id,
                db_models.Event.event_type == constants.EventType.COMMENT_UPDATED,
            )
        )
    assert committed_updates == 0


# ---------------------------------------------------------------------------
# 11. A banned actor is denied at the same boundary, even when the request's
#     role claim still looks authorized.
# ---------------------------------------------------------------------------
def test_banned_actor_comment_write_is_rejected(db):
    comment = comments.create_ticket_comment(
        "ticket",
        models.CommentCreate(body="customer text", visibility=PUBLIC),
        operations.get_user("customer"),
    )
    stale_manager = operations.get_user("manager")
    operations.update_user(
        "manager", {"user_status": constants.UserStatus.BANNED}
    )

    with pytest.raises(AuthorizationError):
        comments.update_comment(
            "ticket",
            comment.id,
            models.CommentUpdate(visibility=INTERNAL),
            stale_manager,
        )

    stored = operations.get_comment(comment.id)
    assert stored.visibility is PUBLIC
    assert stored.body == "customer text"
