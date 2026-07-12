from typing import List, Optional
from sqlalchemy import ForeignKey, String, Time, Interval, Enum, DateTime, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from datetime import datetime, timedelta
from src.constants import Role, Category, Priority, Status, Tag, UserStatus, EventType, EntityType, Visibility, Source
from sqlalchemy.dialects.postgresql import ARRAY


class Base(DeclarativeBase):
    pass

class Ticket(Base):
    __tablename__ = 'tickets'
    id:                 Mapped[str] = mapped_column(String(36), primary_key=True)
    title:              Mapped[str] = mapped_column(String(255))
    description:        Mapped[str] = mapped_column(String(32000))
    category:           Mapped[Category] = mapped_column(Enum(Category))
    tags:               Mapped[str] = mapped_column(String(200), nullable=True)
    assigned_agent_id:  Mapped[Optional[str]] = mapped_column(
                String(36), 
                ForeignKey('users.id', ondelete='SET NULL'),
                nullable=True)
    creator_user_id:    Mapped[str] = mapped_column(
        String(36),
        ForeignKey('users.id', ondelete='RESTRICT')
        )
    status:             Mapped[Status] = mapped_column(Enum(Status))
    priority:           Mapped[Priority] = mapped_column(Enum(Priority))
    updated_at:         Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at:         Mapped[datetime] = mapped_column(DateTime(timezone=True))

    deleted_at:         Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # due_at: Mapped[Optonal[timedelta]] = mapped_column(Interval)

    def __repr__(self):
        desc_short = self.description[:50]
        return (f"Ticket(\n"
                f"  id={self.id!r},\n"
                f"  title={self.title!r},\n"
                f"  description={desc_short!r},\n"
                f"  category={self.category!r},\n"
                f"  tags={self.tags!r},\n"
                f"  assigned_agent_id={self.assigned_agent_id!r},\n"
                f"  creator_user_id={self.creator_user_id!r},\n"
                f"  status={self.status!r},\n"
                f"  priority={self.priority!r},\n"
                f"  updated_at={self.updated_at!r},\n"
                f"  created_at={self.created_at!r}\n"
                f")")

class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    nickname: Mapped[str] = mapped_column(String(128), unique=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str] = mapped_column(String(50))
    last_name: Mapped[str] = mapped_column(String(50))
    phone: Mapped[str] = mapped_column(String(24), unique=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    role: Mapped[Role] = mapped_column(Enum(Role))
    password: Mapped[str] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    user_status: Mapped[UserStatus] = mapped_column(Enum(UserStatus))
   
    def __repr__(self):
        return (f"User(id={self.id!r}, nickname={self.nickname!r}, "
                f"avatar_url={self.avatar_url!r}, first_name={self.first_name!r}, "
                f"last_name={self.last_name!r}, phone={self.phone!r}, "
                f"email={self.email!r}, role={self.role!r}, "
                f"updated_at={self.updated_at!r}, created_at={self.created_at!r})")
    

class Event(Base):
    __tablename__ = 'events'
    id:             Mapped[str] = mapped_column(String(36), primary_key=True)

    entity_type:    Mapped[EntityType] = mapped_column(Enum(EntityType), nullable=False)
    entity_id:      Mapped[str] = mapped_column(String(36), nullable=True) #whcih exact object changed
    actor_user_id:  Mapped[str] = mapped_column(
                        String(36),
                        ForeignKey('users.id', ondelete='RESTRICT'),
                        nullable=False)
    event_type:     Mapped[EventType] = mapped_column(Enum(EventType), nullable=False)
    # PostgreSQL migration: expand these audit payload columns to Text or JSON/JSONB.
    # String(255) is not large enough for serialized values such as comment bodies.
    old_value:      Mapped[str] = mapped_column(String(255), nullable=True)
    batch_id:       Mapped[str] = mapped_column(String(36), nullable=True, default=None)
    new_value:      Mapped[str] = mapped_column(String(255), nullable=False)
    metadata_:      Mapped[str] = mapped_column("metadata", String(200), nullable=True) #additional info
    created_at:     Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Comment(Base):
    __tablename__ = 'comments'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ticket_id: Mapped[str] = mapped_column(
                String(36),
                ForeignKey('tickets.id', ondelete="RESTRICT"),
                nullable=False)
    author_user_id: Mapped[str] = mapped_column(
                String(36),
                ForeignKey('users.id', ondelete='RESTRICT'))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[Visibility] = mapped_column(Enum(Visibility), nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by_user_id: Mapped[str | None] = mapped_column(
                String(36),
                ForeignKey('users.id', ondelete='SET NULL'),
                nullable=True)
    parent_comment_id: Mapped[str | None] = mapped_column(
                String(36),
                ForeignKey('comments.id', ondelete='SET NULL'),
                nullable=True
    )
    attachments_count: Mapped[int] = mapped_column(default=0)
    source: Mapped[Source] = mapped_column(Enum(Source), nullable=False)


# ========================== APP ==============================
class RefreshSession(Base):
    __tablename__ = 'refresh_sessions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
                                        String(36), 
                                        ForeignKey('users.id', ondelete='CASCADE')
                                        )
    refresh_token_hash: Mapped[str] = mapped_column(String(255)) 
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
