from datetime import datetime
from pydantic import BaseModel, Field
from src.constants.enums import Status, Category, Tag, Priority, Role, UserStatus, EventType

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

    updated_at: datetime
    created_at: datetime
    # due_at: datetime

    deleted_at: datetime | None = None

class TicketCreate(BaseModel): #ticket that creates a user
    title: str
    description: str
    category: Category
    status: Status = Status.NEW
    tags: list[Tag] = Field(default_factory=list)
    priority: Priority = Priority.NORMAL

#ticket update only for agents
class TicketUpdate(BaseModel): 
    tags: list[Tag] | None = None 
    assigned_agent_id: str | None = None 
    status: Status | None = None
    priority: Priority | None = None
    deleted_at: datetime | None = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str

class AssignTicketRequest(BaseModel):
    agent_id: str

