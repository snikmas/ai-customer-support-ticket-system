from fastapi.testclient import TestClient
from types import SimpleNamespace
from datetime import datetime, timezone
import pytest

from main import app
from src import constants
from src.exceptions.domain import AlreadyDeletedError, CommentNotFoundError
from src.services import comments as comments_service
from src.routers import tickets as tickets_router


client = TestClient(app)


def test_comment_create_rejects_server_owned_fields(make_user):
    app.dependency_overrides[tickets_router.get_current_user] = lambda: make_user()
    response = client.post(
        "/tickets/ticket-1/comments",
        json={
            "body": "Forged system comment",
            "visibility": constants.Visibility.PUBLIC.value,
            "source": constants.Source.SYSTEM.value,
            "attachments_count": 99,
        },
    )

    assert response.status_code == 422


def test_manager_cannot_read_deleted_comment(monkeypatch, make_user, make_ticket):
    requester = make_user(role=constants.Role.MANAGER)
    ticket = make_ticket()
    now = datetime.now(timezone.utc)
    comment = SimpleNamespace(
        id="comment-1", ticket_id=ticket.id, author_user_id="author",
        body="deleted", visibility=constants.Visibility.PUBLIC,
        edited_at=None, created_at=now, updated_at=now, deleted_at=now,
        deleted_by_user_id=requester.id, parent_comment_id=None,
        attachments_count=0, source=constants.Source.API,
    )
    monkeypatch.setattr(comments_service.operations, "get_comment", lambda comment_id: comment)
    monkeypatch.setattr(comments_service.operations, "get_ticket", lambda ticket_id: ticket)

    try:
        comments_service.get_comment(ticket.id, comment.id, requester)
    except CommentNotFoundError:
        pass
    else:
        raise AssertionError("deleted comment detail must be hidden from managers too")


def test_reply_rejects_parent_from_another_ticket(monkeypatch, make_user, make_ticket):
    requester = make_user(id="customer")
    ticket = make_ticket(id="ticket-1", creator_user_id=requester.id)
    parent = SimpleNamespace(id="parent", ticket_id="ticket-2")
    monkeypatch.setattr(comments_service.operations, "get_ticket", lambda ticket_id: ticket)
    monkeypatch.setattr(comments_service.operations, "get_comment", lambda comment_id: parent)

    comment_create = comments_service.api_models.CommentCreate(
        body="Reply",
        visibility=constants.Visibility.PUBLIC,
        parent_comment_id=parent.id,
    )
    try:
        comments_service.create_ticket_comment(ticket.id, comment_create, requester)
    except CommentNotFoundError:
        pass
    else:
        raise AssertionError("a reply parent must belong to the same ticket")


def test_get_ticket_comments_requires_authentication():
    response = client.get("/tickets/ticket-1/comments")

    assert response.status_code == 401


def test_get_ticket_comments_passes_nested_path_and_pagination(monkeypatch, make_user):
    requester = make_user(id="requester-1")
    captured = {}

    app.dependency_overrides[tickets_router.get_current_user] = lambda: requester

    def fake_get_all_comments(ticket_id, current_user, limit, offset, sort_by, sort_order):
        captured.update(
            {
                "ticket_id": ticket_id,
                "current_user": current_user,
                "limit": limit,
                "offset": offset,
                "sort_by": sort_by,
                "sort_order": sort_order,
            }
        )
        return [{"id": "comment-1", "ticket_id": ticket_id, "body": "hello"}]

    monkeypatch.setattr(tickets_router.s_comments, "get_all_comments", fake_get_all_comments)

    response = client.get(
        "/tickets/ticket-1/comments",
        params={
            "limit": 5,
            "offset": 10,
            "sort_by": "updated_at",
            "sort_order": "asc",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"][0]["id"] == "comment-1"
    assert captured == {
        "ticket_id": "ticket-1",
        "current_user": requester,
        "limit": 5,
        "offset": 10,
        "sort_by": "updated_at",
        "sort_order": "asc",
    }


def test_create_ticket_comment_uses_body_and_requester(monkeypatch, make_user):
    requester = make_user(id="author-1")
    captured = {}

    app.dependency_overrides[tickets_router.get_current_user] = lambda: requester

    def fake_create_ticket_comment(ticket_id, comment_create, current_user):
        captured["ticket_id"] = ticket_id
        captured["comment_create"] = comment_create
        captured["requester"] = current_user
        return {"id": "comment-1", "ticket_id": ticket_id, "body": comment_create.body}

    monkeypatch.setattr(tickets_router.s_comments, "create_ticket_comment", fake_create_ticket_comment)

    response = client.post(
        "/tickets/ticket-1/comments",
        json={
            "body": "New comment",
            "visibility": constants.Visibility.PUBLIC.value,
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["data"]["body"] == "New comment"
    assert captured["ticket_id"] == "ticket-1"
    assert captured["comment_create"].visibility == constants.Visibility.PUBLIC
    assert captured["requester"] is requester


def test_update_ticket_comment_passes_nested_ids_body_and_requester(monkeypatch, make_user):
    requester = make_user(id="author-1")
    captured = {}

    app.dependency_overrides[tickets_router.get_current_user] = lambda: requester

    def fake_update_comment(ticket_id, comment_id, new_info, current_user):
        captured["ticket_id"] = ticket_id
        captured["comment_id"] = comment_id
        captured["new_info"] = new_info
        captured["requester"] = current_user
        return {"id": comment_id, "ticket_id": ticket_id, "body": new_info.body}

    monkeypatch.setattr(tickets_router.s_comments, "update_comment", fake_update_comment)

    response = client.patch(
        "/tickets/ticket-1/comments/comment-1",
        json={"body": "Edited comment"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["body"] == "Edited comment"
    assert captured["ticket_id"] == "ticket-1"
    assert captured["comment_id"] == "comment-1"
    assert captured["new_info"].body == "Edited comment"
    assert captured["requester"] is requester


def test_get_ticket_comment_translates_domain_exception(monkeypatch, make_user):
    requester = make_user(id="requester-1")

    app.dependency_overrides[tickets_router.get_current_user] = lambda: requester

    def fake_get_comment(ticket_id, comment_id, current_user):
        raise CommentNotFoundError()

    monkeypatch.setattr(tickets_router.s_comments, "get_comment", fake_get_comment)

    response = client.get("/tickets/ticket-1/comments/missing-comment")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "comment_not_found",
            "message": "Comment not found",
        }
    }


def test_delete_ticket_comment_passes_nested_ids_and_requester(monkeypatch, make_user):
    requester = make_user(id="author-1")
    captured = {}

    app.dependency_overrides[tickets_router.get_current_user] = lambda: requester

    def fake_delete_comment(ticket_id, comment_id, current_user):
        captured["ticket_id"] = ticket_id
        captured["comment_id"] = comment_id
        captured["requester"] = current_user
        return True

    monkeypatch.setattr(tickets_router.s_comments, "delete_comment", fake_delete_comment)

    response = client.delete("/tickets/ticket-1/comments/comment-1")

    assert response.status_code == 200, response.text
    assert response.json()["data"] is True
    assert captured == {
        "ticket_id": "ticket-1",
        "comment_id": "comment-1",
        "requester": requester,
    }


def test_repeated_comment_delete_is_rejected_before_new_event(monkeypatch, make_user):
    requester = make_user(id="author-1")
    comment = SimpleNamespace(
        id="comment-1",
        ticket_id="ticket-1",
        author_user_id=requester.id,
        deleted_at=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(comments_service.operations, "get_comment", lambda _: comment)
    monkeypatch.setattr(
        comments_service.operations,
        "delete_comment_with_event",
        lambda *_: pytest.fail("a repeated delete must not write another event"),
    )

    with pytest.raises(AlreadyDeletedError):
        comments_service.delete_comment("ticket-1", "comment-1", requester)
