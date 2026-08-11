from datetime import datetime
from pydantic import BaseModel, ConfigDict, model_validator
from typing import Any
from src.constants.enums import ActorType, Status, Category, Tag, Priority, Role, UserStatus, EntityType, EventType
from .validation import EmailAddress, LoginPassword, Nickname, RefreshToken


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nickname: Nickname | None = None
    email: EmailAddress | None = None
    password: LoginPassword

    @model_validator(mode="after")
    def require_one_identifier(self):
        if (self.nickname is None) == (self.email is None):
            raise ValueError("provide_exactly_one_login_identifier")
        return self

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class Notification(BaseModel):
    id: str
    notification_type: str
    ticket_id: str | None = None
    message: str
    created_at: datetime
    read_at: datetime | None = None


class NotificationMarkRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    read: bool = True

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

class LogoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: RefreshToken
    

class Event(BaseModel):
    id: str
    entity_type: EntityType
    entity_id: str | None = None
    actor_type: ActorType = ActorType.HUMAN
    actor_user_id: str | None
    event_type: EventType
    old_value: str | None = None
    new_value: str
    batch_id: str | None = None
    metadata: str | None = None
    idempotency_key: str | None = None
    created_at: datetime

    @model_validator(mode="after")
    def validate_actor_contract(self):
        if self.actor_type is ActorType.HUMAN and self.actor_user_id is None:
            raise ValueError("human_actor_requires_user_id")
        if self.actor_type is ActorType.SYSTEM and self.actor_user_id is not None:
            raise ValueError("system_actor_cannot_have_user_id")
        return self


class TicketHistoryEvent(BaseModel):
    id: str
    entity_type: EntityType
    entity_id: str | None = None
    actor_type: ActorType
    actor_user_id: str | None = None
    event_type: EventType
    old_value: dict[str, Any] | None = None
    new_value: dict[str, Any]
    metadata: str | None = None
    created_at: datetime
