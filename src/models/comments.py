from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from src.constants.enums import Status, Category, Tag, Priority, Role, UserStatus, EventType, Visibility, Source
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
