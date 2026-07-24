from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator
from src.constants.enums import Status, Category, Tag, Priority, Role, UserStatus, EventType, AnalysisStatus
from .validation import EntityId, LongBody, RefreshToken, TicketTitle

class Ticket(BaseModel):
    id: str
    title: str
    description: str
    category: Category
    tags: list[Tag]
    department_id: str | None = None
    skill_ids: list[str] = Field(default_factory=list)

    assigned_agent_id: str | None = None # cor assignee_id
    creator_user_id: str
    status: Status = Status.NEW
    priority: Priority = Priority.NORMAL

    updated_at: datetime
    created_at: datetime
    due_at: datetime | None = None
    is_overdue: bool = False

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
    department_id: EntityId | None = None
    skill_ids: list[EntityId] | None = Field(default=None, max_length=20)

    @field_validator("skill_ids")
    @classmethod
    def reject_duplicate_skill_ids(cls, value: list[str] | None):
        if value is not None and len(value) != len(set(value)):
            raise ValueError("duplicate_skill_ids")
        return value


class RefreshTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: RefreshToken

class AssignTicketRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: EntityId


class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra='forbid', from_attributes=True)

    id: str
    summary: str | None
    error_code: str | None
    error_message: str | None
    ticket_id: str | None
    job_id: str | None
    provider: str | None
    model: str | None
    prompt_version: str | None
    input_tokens: int | None
    output_tokens: int | None
    requester_id: str | None
    attempt_count: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime
    status: AnalysisStatus
