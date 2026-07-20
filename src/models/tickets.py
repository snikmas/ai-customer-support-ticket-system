from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from src.constants.enums import Status, Category, Tag, Priority, Role, UserStatus, EventType, AnalysisStatus
from .validation import EntityId, LongBody, RefreshToken, TicketTitle

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
    due_at: datetime | None = None

    deleted_at: datetime | None = None

class TicketCreate(BaseModel): #ticket that creates a user
    model_config = ConfigDict(extra="forbid")

    title: TicketTitle
    description: LongBody
    category: Category
    tags: list[Tag] = Field(default_factory=list, max_length=10)

#ticket update only for agents
class TicketUpdate(BaseModel): 
    model_config = ConfigDict(extra="forbid")

    tags: list[Tag] | None = Field(default=None, max_length=10)
    assigned_agent_id: str | None = None 
    status: Status | None = None
    priority: Priority | None = None
    deleted_at: datetime | None = None


class RefreshTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: RefreshToken

class AssignTicketRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: EntityId


class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra='forbid')

    id: str
    summary: str
    full_description: str
    ticket_id: str
    job_id: str
    requester_id: str
    created_at: datetime
    status: AnalysisStatus
