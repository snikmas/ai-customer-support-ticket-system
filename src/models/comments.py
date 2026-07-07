from datetime import datetime
from pydantic import BaseModel
from src.constants.enums import Status, Category, Tag, Priority, Role, UserStatus, EventType, Visibility, Source

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
    body: str
    visibility: Visibility

    parent_comment_id: str | None = None
    attachments_count: int | None = None
    source: Source

class CommentUpdate(BaseModel):
    body: str | None = None
    visibility: Visibility | None = None
