from types import SimpleNamespace

import pytest

from src.exceptions.domain import NotificationNotFoundError
from src.services import notifications


def test_notification_service_only_marks_recipient_notification(monkeypatch, make_user):
    requester = make_user(id="user-1")
    captured = {}

    def fake_mark(notification_id, recipient_id):
        captured.update(notification_id=notification_id, recipient_id=recipient_id)
        return SimpleNamespace(
            id=notification_id,
            notification_type="comment",
            ticket_id="ticket-1",
            message="A new comment is available",
            created_at=requester.created_at,
            read_at=requester.updated_at,
        )

    monkeypatch.setattr(notifications.operations, "mark_notification_read", fake_mark)

    result = notifications.mark_read("notification-1", requester)

    assert result.id == "notification-1"
    assert captured == {"notification_id": "notification-1", "recipient_id": requester.id}


def test_notification_service_hides_other_users_notification(monkeypatch, make_user):
    requester = make_user(id="user-1")
    monkeypatch.setattr(notifications.operations, "mark_notification_read", lambda *_: None)

    with pytest.raises(NotificationNotFoundError):
        notifications.mark_read("other-user-notification", requester)
