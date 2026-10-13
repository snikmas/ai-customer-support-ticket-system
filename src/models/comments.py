from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_validator
from src.constants.enums import Visibility, Source
from .validation import EntityId, LongBody

class Comment(BaseModel):
    id: str
    ticket_id: str
    author_user_id: str
    body: str
    visibility: Visibility

    edited_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

    deleted_by_user_id: str | None = None
    parent_comment_id: str | None = None
    attachments_count: int | None = None
    source: Source

class CommentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: LongBody
    visibility: Visibility

    parent_comment_id: EntityId | None = None

class CommentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: LongBody | None = None
    visibility: Visibility | None = None

    @field_validator("body", "visibility")
    @classmethod
    def reject_explicit_null(cls, value):
        if value is None:
            raise ValueError("comment_field_cannot_be_null")
        return value


class AttachmentResponse(BaseModel):
    id: str
    comment_id: str
    original_filename: str
    content_type: str
    size_bytes: int
    created_at: datetime
