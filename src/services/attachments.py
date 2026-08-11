from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from fastapi import UploadFile

from src import constants, models
from src.core.config import ATTACHMENTS_DIR
from src.db import models as db_models, operations
from src.exceptions.domain import (
    AttachmentNotFoundError,
    AttachmentValidationError,
    AuthorizationError,
    InternalOperationError,
)
from src.services import comments as comments_service
from src.services import tickets as tickets_service
from src.storage import LocalAttachmentStorage

MAX_ATTACHMENT_SIZE = 5 * 1024 * 1024
MAX_ATTACHMENTS_PER_COMMENT = 5
ALLOWED_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".json": "application/json",
}

storage = LocalAttachmentStorage(ATTACHMENTS_DIR)


def _safe_filename(filename: str | None) -> tuple[str, str, str]:
    raw = Path(filename or "attachment").name
    safe = "".join(character for character in raw if character.isprintable()).strip()
    if not safe:
        safe = "attachment"
    safe = safe[:255]
    extension = Path(safe).suffix.lower()
    content_type = ALLOWED_TYPES.get(extension)
    if content_type is None:
        raise AttachmentValidationError(
            "File type is not allowed. Use PDF, PNG, JPEG, TXT, CSV, or JSON.",
            code="attachment_type_not_allowed",
        )
    return safe, extension, content_type


def _response(attachment: db_models.Attachment) -> models.AttachmentResponse:
    return models.AttachmentResponse.model_validate(attachment, from_attributes=True)


async def upload_attachment(
    ticket_id: str,
    comment_id: str,
    upload: UploadFile,
    requester: models.User,
) -> models.AttachmentResponse:
    # Both checks are intentional: the ticket check applies ticket visibility,
    # while the comment check applies comment visibility.
    tickets_service.get_ticket(ticket_id, requester)
    comment = comments_service.get_comment(ticket_id, comment_id, requester)
    if comment.deleted_at is not None:
        raise AttachmentNotFoundError()
    if operations.count_comment_attachments(comment_id) >= MAX_ATTACHMENTS_PER_COMMENT:
        raise AttachmentValidationError(
            f"A comment can have at most {MAX_ATTACHMENTS_PER_COMMENT} files",
            code="attachment_count_exceeded",
        )

    filename, extension, content_type = _safe_filename(upload.filename)
    received = await upload.read(MAX_ATTACHMENT_SIZE + 1)
    if len(received) > MAX_ATTACHMENT_SIZE:
        raise AttachmentValidationError(
            f"Each attachment must be at most {MAX_ATTACHMENT_SIZE // (1024 * 1024)} MiB",
            code="attachment_size_exceeded",
        )
    if upload.content_type and upload.content_type != content_type:
        raise AttachmentValidationError(
            "The declared MIME type does not match the filename extension",
            code="attachment_mime_mismatch",
        )

    now = constants.utc_now()
    attachment = db_models.Attachment(
        id=constants.generate_id(),
        comment_id=comment_id,
        storage_key=f"{uuid4().hex}{extension}",
        original_filename=filename,
        content_type=content_type,
        size_bytes=len(received),
        created_by_user_id=requester.id,
        created_at=now,
        deleted_at=None,
    )
    storage.save(attachment.storage_key, received)
    event = models.Event(
        id=constants.generate_id(),
        entity_type=constants.EntityType.ATTACHMENT,
        entity_id=attachment.id,
        actor_user_id=requester.id,
        event_type=constants.EventType.ATTACHMENT_ADDED,
        old_value=None,
        new_value=constants._audit_json({
            "comment_id": comment_id,
            "content_type": content_type,
            "size_bytes": len(received),
        }),
        metadata=None,
        created_at=now,
    )
    try:
        return _response(operations.create_attachment(attachment, event))
    except Exception as exc:
        # Metadata insertion failed, so do not leave an unreferenced local blob.
        storage.delete(attachment.storage_key)
        raise InternalOperationError(
            "Attachment could not be saved",
            code="attachment_save_failed",
        ) from exc


def list_attachments(
    ticket_id: str,
    comment_id: str,
    requester: models.User,
) -> list[models.AttachmentResponse]:
    tickets_service.get_ticket(ticket_id, requester)
    comments_service.get_comment(ticket_id, comment_id, requester)
    return [_response(item) for item in operations.get_comment_attachments(comment_id)]


def download_attachment(
    ticket_id: str,
    comment_id: str,
    attachment_id: str,
    requester: models.User,
) -> tuple[Path, db_models.Attachment, str]:
    tickets_service.get_ticket(ticket_id, requester)
    comments_service.get_comment(ticket_id, comment_id, requester)
    attachment = operations.get_attachment(attachment_id)
    if attachment is None or attachment.comment_id != comment_id or attachment.deleted_at is not None:
        raise AttachmentNotFoundError()
    try:
        path = storage.path(attachment.storage_key)
    except FileNotFoundError as exc:
        raise AttachmentNotFoundError("Attachment bytes are no longer available") from exc
    ascii_name = "".join(character if ord(character) < 128 and character.isprintable() else "_" for character in attachment.original_filename)
    disposition = f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(attachment.original_filename)}'
    return path, attachment, disposition
