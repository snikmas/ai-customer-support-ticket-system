from typing import List, Optional
from sqlalchemy import ForeignKey, String, Time, Interval, Enum, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from datetime import datetime, timedelta
from src.constants import Role, Category, Priority, Status, Tag 

class Base(DeclarativeBase):
    pass

class Ticket(Base):
    __tablename__ = 'tickets'
    id: Mapped[str] = mapped_column(str, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(32000))
    category: Mapped[Category] = mapped_column(Enum(Category))
    tags: Mapped[List[str]] = mapped_column(str, nullable=True)
    assigned_agent_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey('users.id', ondelete='NOTHING'),
        String(36), 
        nullable=True)
    creator_user_id: Mapped[str] = mapped_column(
        ForeignKey('user.id', ondelete='NOTHING'), 
        String(36))
    status: Mapped[Status] = mapped_column(Enum(Status))
    priority: Mapped[Priority] = mapped_column(Enum(Priority))

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # due_at: Mapped[Optonal[timedelta]] = mapped_column(Interval)

    def __repr__(self) -> str:
        pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(primary_key=True)
    nickname: Mapped[str] = mapped_column(String(128), unique=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str] = mapped_column(String(50))
    last_name: Mapped[str] = mapped_column(String(50))
    phone: Mapped[str] = mapped_column(String(24), unique=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    role: Mapped[Role] = mapped_column(Enum(Role))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    def __repr__(self) -> str:
        pass