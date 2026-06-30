from typing import List, Optional
from sqlalchemy import ForeignKey, String, Time, Interval, Enum, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from datetime import datetime, timedelta
from src.constants import Role, Category, Priority, Status, Tag 
from sqlalchemy.dialects.postgresql import ARRAY

class Base(DeclarativeBase):
    pass

class Ticket(Base):
    __tablename__ = 'tickets'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(32000))
    category: Mapped[Category] = mapped_column(Enum(Category))
    # tags: Mapped[List[str]] = mapped_column(ARRAY(String(50)), nullable=True)
    tags: Mapped[str] = mapped_column(String(200), nullable=True)
    assigned_agent_id: Mapped[Optional[str]] = mapped_column(
        String(36), 
        ForeignKey('users.id', ondelete='NOTHING'),
        nullable=True)
    creator_user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('users.id', ondelete='NOTHING')
        )
    status: Mapped[Status] = mapped_column(Enum(Status))
    priority: Mapped[Priority] = mapped_column(Enum(Priority))

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
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
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
   
    def __repr__(self):
        return (f"User(id={self.id!r}, nickname={self.nickname!r}, "
                f"avatar_url={self.avatar_url!r}, first_name={self.first_name!r}, "
                f"last_name={self.last_name!r}, phone={self.phone!r}, "
                f"email={self.email!r}, role={self.role!r}, "
                f"updated_at={self.updated_at!r}, created_at={self.created_at!r})")