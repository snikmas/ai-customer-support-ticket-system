from src import models
from src.db import operations
from src.exceptions.domain import NotificationNotFoundError
from src.constants import logger


def emit(
    recipient_user_id: str,
    notification_type: str,
    message: str,
    *,
    ticket_id: str | None = None,
    idempotency_key: str | None = None,
) -> None:
    """Best-effort side effect; the ticket/comment transaction stays primary."""
    try:
        operations.create_notification(
            recipient_user_id,
            notification_type,
            message,
            ticket_id=ticket_id,
            idempotency_key=idempotency_key,
        )
    except Exception:
        logger.exception(
            "Notification delivery failed",
            extra={"recipient_user_id": recipient_user_id, "notification_type": notification_type},
        )


def _to_response(notification) -> models.Notification:
    return models.Notification.model_validate(notification, from_attributes=True)


def list_for_user(
    requester: models.User,
    limit: int,
    offset: int,
    unread_only: bool = False,
) -> list[models.Notification]:
    return [
        _to_response(item)
        for item in operations.list_notifications(
            requester.id, limit, offset, unread_only=unread_only
        )
    ]


def unread_count(requester: models.User) -> int:
    return operations.count_unread_notifications(requester.id)


def mark_read(notification_id: str, requester: models.User) -> models.Notification:
    item = operations.mark_notification_read(notification_id, requester.id)
    if item is None:
        raise NotificationNotFoundError()
    return _to_response(item)


def mark_all_read(requester: models.User) -> int:
    return operations.mark_all_notifications_read(requester.id)
