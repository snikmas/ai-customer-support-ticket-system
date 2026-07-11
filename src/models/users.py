from datetime import datetime
from pydantic import BaseModel, ConfigDict
from src.constants.enums import Status, Category, Tag, Priority, Role, UserStatus
from .validation import AvatarUrl, EmailAddress, NewPassword, Nickname, PersonName, PhoneNumber


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
