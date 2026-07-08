from datetime import datetime
from pydantic import BaseModel
from src.constants.enums import Status, Category, Tag, Priority, Role, UserStatus


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
    nickname: str
    avatar_url: str | None = None
    first_name: str
    last_name: str
    password: str

    phone: str
    email: str

class UserUpdate(BaseModel):
    nickname: str | None = None
    avatar_url: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    password: str | None = None

    role: str | None = None
    phone: str | None = None
    email: str | None = None
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
