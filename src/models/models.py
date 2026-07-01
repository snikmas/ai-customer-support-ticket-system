from datetime import datetime
from pydantic import BaseModel
from src.constants.enums import Status, Category, Tag, Priority, Role

class Ticket(BaseModel):
    id: str
    title: str
    description: str
    category: Category
    tags: list[Tag]

    assigned_agent_id: str | None = None # cor assignee_id
    creator_user_id: str
    status: Status = Status.NEW
    priority: Priority = Priority.NORMAL
    password: str

    updated_at: datetime
    created_at: datetime
    due_at: datetime

class TicketCreate(BaseModel): #ticket that creates a user
    title: str
    description: str
    category: Category
    status: Status = Status.NEW
    tags: list[Tag] | None = []
    priority: Priority = Priority.NORMAL

#ticket update only for agents
class TicketUpdate(BaseModel): 
    tags: list[Tag] | None = None 
    assigned_agent_id: str | None = None 
    status: Status | None = None
    priority: Priority | None = None

# =====================================================
# ==================== USER ===========================
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

