from datetime import datetime
from pydantic import BaseModel
from src.constants.enums import Status, Category, Tag, Priority, Role, UserStatus, EntityType, EventType


class LoginRequest(BaseModel):
    nickname: str | None = None
    email: str | None = None
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshSession(BaseModel):
    id: str
    user_id: str
    refresh_token_hash: str
    expires_at: datetime
    revoked_at: datetime | None = None
    created_at: datetime

class CreatedRefreshSession(BaseModel):
    refresh_session_id: str
    refresh_token: str


class Event(BaseModel):
    id: str
    entity_type: EntityType
    entity_id: str | None = None
    actor_user_id: str
    event_type: EventType
    old_value: str | None = None
    new_value: str
    batch_id: str | None = None
    metadata: str | None = None
    created_at: datetime

