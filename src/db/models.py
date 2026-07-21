from typing import List, Optional
from sqlalchemy import CheckConstraint, Column, ForeignKey, String, Time, Interval, Enum, DateTime, Table, Text
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from datetime import datetime, timedelta, timezone
from src.constants import (
    Role, 
    Category, 
    Priority, 
    Status, 
    Tag, 
    UserStatus, 
    EventType, 
    EntityType,
    Visibility, 
    Source,
    AnalysisStatus,
    ActorType,
    AvailabilityStatus,
    )
from sqlalchemy.dialects.postgresql import ARRAY


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """Keep timezone-aware UTC datetimes when SQLite drops the offset."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("UTCDateTime requires a timezone-aware datetime")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


agent_skills = Table(
    "agent_skills",
    Base.metadata,
    Column(
        "agent_user_id",
        String(36),
        ForeignKey("agent_profiles.user_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "skill_id",
        String(36),
        ForeignKey("skills.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
)


ticket_skills = Table(
    "ticket_skills",
    Base.metadata,
    Column(
        "ticket_id",
        String(36),
        ForeignKey("tickets.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "skill_id",
        String(36),
        ForeignKey("skills.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
)


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)


class Ticket(Base):
    __tablename__ = 'tickets'
    id:                 Mapped[str] = mapped_column(String(36), primary_key=True)
    title:              Mapped[str] = mapped_column(String(255))
    description:        Mapped[str] = mapped_column(String(32000))
    category:           Mapped[Category] = mapped_column(Enum(Category))
    tags:               Mapped[str] = mapped_column(String(200), nullable=True)
    department_id:      Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=True,
    )
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
    due_at:             Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime(),
        nullable=True,
    )

    deleted_at:         Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    requested_skills: Mapped[List["Skill"]] = relationship(
        secondary=ticket_skills,
        lazy="selectin",
    )

    @property
    def skill_ids(self) -> list[str]:
        return [skill.id for skill in self.requested_skills]

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
    agent_profile: Mapped[Optional["AgentProfile"]] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        single_parent=True,
    )
   
    def __repr__(self):
        return (f"User(id={self.id!r}, nickname={self.nickname!r}, "
                f"avatar_url={self.avatar_url!r}, first_name={self.first_name!r}, "
                f"last_name={self.last_name!r}, phone={self.phone!r}, "
                f"email={self.email!r}, role={self.role!r}, "
                f"updated_at={self.updated_at!r}, created_at={self.created_at!r})")


class AgentProfile(Base):
    __tablename__ = "agent_profiles"

    # Using the foreign key as the primary key guarantees one profile per user.
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    availability_status: Mapped[AvailabilityStatus] = mapped_column(
        Enum(AvailabilityStatus),
        nullable=False,
    )
    availability_reason: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    availability_note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    unavailable_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    max_active_tickets: Mapped[int] = mapped_column(nullable=False, default=0)
    last_assigned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    department_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped["User"] = relationship(back_populates="agent_profile")
    skills: Mapped[List["Skill"]] = relationship(
        secondary=agent_skills,
        lazy="selectin",
    )

    @property
    def skill_ids(self) -> list[str]:
        return [skill.id for skill in self.skills]
    

class Event(Base):
    __tablename__ = 'events'
    __table_args__ = (
        CheckConstraint(
            "(actor_type = 'HUMAN' AND actor_user_id IS NOT NULL) OR "
            "(actor_type = 'SYSTEM' AND actor_user_id IS NULL)",
            name="ck_events_actor_contract",
        ),
    )
    id:             Mapped[str] = mapped_column(String(36), primary_key=True)

    entity_type:    Mapped[EntityType] = mapped_column(Enum(EntityType), nullable=False)
    entity_id:      Mapped[str] = mapped_column(String(36), nullable=True) #whcih exact object changed
    actor_type:     Mapped[ActorType] = mapped_column(
                        Enum(ActorType),
                        nullable=False,
                        default=ActorType.HUMAN)
    actor_user_id:  Mapped[Optional[str]] = mapped_column(
                        String(36),
                        ForeignKey('users.id', ondelete='RESTRICT'),
                        nullable=True)
    event_type:     Mapped[EventType] = mapped_column(Enum(EventType), nullable=False)
    # Audit snapshots can include a short note plus several routing fields, so a
    # 255-character column is too small even when every individual field is bounded.
    old_value:      Mapped[str] = mapped_column(Text, nullable=True)
    batch_id:       Mapped[str] = mapped_column(String(36), nullable=True, default=None)
    new_value:      Mapped[str] = mapped_column(Text, nullable=False)
    metadata_:      Mapped[str] = mapped_column("metadata", String(200), nullable=True) #additional info
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, unique=True)
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
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    revoked_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())


# =================================================================
class AnalysisResult(Base):
    __tablename__ = 'analysis_result'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    summary: Mapped[str] = mapped_column(String(300))
    full_description: Mapped[str] = mapped_column(String(2000))
    ticket_id: Mapped[str] = mapped_column(
                                String(36),
                                ForeignKey('tickets.id', ondelete='SET NULL')
                                )
    job_id: Mapped[str] = mapped_column(String(36))
    requester_id: Mapped[str] = mapped_column(
                                String(36),
                                ForeignKey('users.id', ondelete='SET NULL')
                                )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[AnalysisStatus] = mapped_column(Enum(AnalysisStatus))
                                
