from sqlalchemy.orm import Session
from .engine import engine
from .models import Ticket, User
from typing import Tuple
from sqlalchemy import Row, select, delete
from datetime import datetime

# from db.utils import reset_database

# ==============================================================
# ======================= USER =================================
def create_user(user_data: User) -> None:
    with Session(engine) as session:
        user = User(
            id=user_data.id,
            nickname=user_data.nickname,
            avatar_url=user_data.avatar_url,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            phone=user_data.phone,
            email=user_data.email,
            role=user_data.role,
            updated_at=user_data.updated_at,
            created_at=user_data.created_at
        )

        session.add(user)
        session.commit()

def get_user(id: str) -> (User | None):
    with Session(engine) as session:
        result = session.get(User, id)
        return result

def get_users() -> {list[User] | None}:
    with Session(engine) as session:
        query = select(User)
        return session.scalars(query).all()

def update_user(id: str, new_info: dict) -> None:
    with Session(engine) as session:
        user = session.get(User, id)

        if user is None:
            return
        
        for field, value in new_info.items():
            setattr(user, field, value)
            
        user.updated_at = datetime.now()
        session.commit()
        return


def delete_user(id: str) -> None:
    with Session(engine) as session:
        # more layer safety:
        user = session.get(User, id)
        if user is None:
            return 
        
        session.delete(user)
        session.commit()
        
def delete_all_users() -> int:
    with Session(engine) as session:
        result = session.execute(delete(User))
        session.commit()
        return result.rowcount


# ==============================================================
# ======================= TICKETS ==============================

def create_ticket(ticket_data: Ticket) -> None:
    with Session(engine) as session:
        ticket = Ticket(
            id=ticket_data.id,
            title=ticket_data.title,
            description=ticket_data.description,
            category=ticket_data.category,
            tags=ticket_data.tags,
            assigned_agent_id=ticket_data.assigned_agent_id,
            creator_user_id=ticket_data.creator_user_id,
            status=ticket_data.status,
            priority=ticket_data.priority,
            updated_at=ticket_data.updated_at,
            created_at=ticket_data.created_at
        )

        session.add(ticket)
        session.commit()


def get_ticket(id: str) -> (Ticket | None):
    with Session(engine) as session:
        result = session.get(Ticket, id)
        return result
    
def get_tickets() -> {list(User) | None}:
    with Session(engine) as session:
        query = select(Ticket)
        return session.scalars(query).all()

def update_ticket(id: str, new_info: dict) -> None:
    with Session(engine) as session:
        ticket = session.get(Ticket, id)

        if ticket is None:
            return
        
        for field, value in new_info.items():
            setattr(ticket, field, value)
        ticket.updated_at = datetime.now()

        session.commit()
        return


def delete_ticket(id: str) -> None:
    with Session(engine) as session:
        ticket = session.get(Ticket, id)
        if ticket is None:
            return
        
        session.delete(ticket)
        session.commit()

def delete_all_tickets() -> int:
    with Session(engine) as session:
        result = session.execute(delete(Ticket))
        session.commit()
        return result.rowcount