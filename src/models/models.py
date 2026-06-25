from datetime import datetime
from fastapi import FastAPI
from pydantic import BaseModel
from src.constants.enums import Status, Category, Tag, Priority


class TicketCreate(BaseModel): #ticket that creates a user
    title: str
    description: str
    category: Category
    tags: list[Tag] | None = []
    # created at? or no need cuz a user


class Ticket(BaseModel):
    id: str
    title: str
    description: str
    category: Category
    tags: list[Tag]


    assigned_agent_id: str = None # cor assignee_id
    status: Status = Status.NEW
    priority: Priority = Priority.NORMAL

    updated_at: datetime
    created_at: datetime
    due_at: datetime

    

class Agent(BaseModel):
    id: str
    nickname: str
    avatar_url: str | None = None
    first_name: str
    last_name: str
    created_at: str
    role: str # later put what kind of
    phone: str
    email: str
    created_at: str


class Client(BaseModel):
    id: str
    nickname: str
    avatar_url: str | None = None
    first_name: str
    last_name: str

    phone: str | None = None
    email: str
    created_at: str
