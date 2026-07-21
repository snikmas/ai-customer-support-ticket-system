from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator
from src.constants.enums import AvailabilityReason, AvailabilityStatus, Role, UserStatus
from .validation import AvatarUrl, EmailAddress, EntityId, NewPassword, Nickname, PersonName, PhoneNumber


class User(BaseModel):
    id: str
    nickname: str
    avatar_url: str | None = None
    first_name: str
    last_name: str

    phone: str
    email: str
    role: Role
    password: str
    updated_at: datetime
    created_at: datetime

    deleted_at: datetime | None = None
    user_status: UserStatus | None = UserStatus.ACTIVE

class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nickname: Nickname
    avatar_url: AvatarUrl | None = None
    first_name: PersonName
    last_name: PersonName
    password: NewPassword

    phone: PhoneNumber
    email: EmailAddress

class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nickname: Nickname | None = None
    avatar_url: AvatarUrl | None = None
    first_name: PersonName | None = None
    last_name: PersonName | None = None
    password: NewPassword | None = None

    role: Role | None = None
    phone: PhoneNumber | None = None
    email: EmailAddress | None = None
    user_status: UserStatus | None = None

class UserResponse(BaseModel):
    id: str
    nickname: str
    avatar_url: str | None = None
    first_name: str
    last_name: str

    phone: str
    email: str
    role: Role
    updated_at: datetime
    created_at: datetime
    deleted_at: datetime | None = None
    user_status: UserStatus | None = UserStatus.ACTIVE


class AgentAvailabilityUpdate(BaseModel):
    """Fields an agent may update for themselves.

    The note is intentionally short. It is operational context for routing,
    not a place for medical or other sensitive personal information.
    """

    model_config = ConfigDict(extra="forbid")

    availability_status: AvailabilityStatus
    reason: AvailabilityReason | None = None
    note: str | None = Field(default=None, max_length=200)
    unavailable_until: datetime | None = None


class AgentProfileManagementUpdate(BaseModel):
    """Routing settings reserved for managers and administrators."""

    model_config = ConfigDict(extra="forbid")

    max_active_tickets: int | None = Field(default=None, ge=0, le=100)
    department_id: EntityId | None = None
    skill_ids: list[EntityId] | None = Field(default=None, max_length=50)

    @field_validator("skill_ids")
    @classmethod
    def reject_duplicate_skill_ids(cls, value: list[str] | None):
        if value is not None and len(value) != len(set(value)):
            raise ValueError("duplicate_skill_ids")
        return value


class AgentProfileResponse(BaseModel):
    user_id: str
    availability_status: AvailabilityStatus
    availability_reason: str | None = None
    availability_note: str | None = None
    unavailable_until: datetime | None = None
    max_active_tickets: int
    last_assigned_at: datetime | None = None
    department_id: str | None = None
    skill_ids: list[str] = Field(default_factory=list)
    current_active_tickets: int
    can_receive_new_tickets: bool
    created_at: datetime
    updated_at: datetime
