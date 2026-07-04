from sqlalchemy.orm import Session
from .engine import engine
from .models import Ticket, User, RefreshSession, UserStatus
from sqlalchemy import Row, select, delete, update
from datetime import datetime, timezone
from src.constants import Status

# ==============================================================
# ======================= SYSTEM ===============================
def create_refresh_session(old_refresh_session: RefreshSession) -> RefreshSession | None:
    refresh_session = None
    with Session(engine) as session:
        refresh_session = RefreshSession(
            id=old_refresh_session.id,
            user_id=old_refresh_session.user_id,
            refresh_token_hash=old_refresh_session.refresh_token_hash,
            expires_at=old_refresh_session.expires_at,
            revoked_at=old_refresh_session.revoked_at,
            created_at=old_refresh_session.created_at
        )
        session.add(refresh_session)
        session.commit()
    return refresh_session

def get_refresh_session_by_id(refresh_session_id: str) -> RefreshSession | None:
    with Session(engine) as session:
        return session.query(RefreshSession).filter_by(id=refresh_session_id).first()

def get_refresh_session_by_hash_refresh_token(hash_token: str) -> RefreshSession | None:
    with Session(engine) as session:
        return session.query(RefreshSession).filter_by(refresh_token_hash=hash_token).first()
    
def revoke_refresh_session(session_id: str) -> bool:
    with Session(engine) as session:
        refresh_session = get_refresh_session_by_id(session_id)
        if refresh_session is None: 
            return False
        session.delete(refresh_session)
        session.commit()
        return True

def rotate_refresh_session(session_id, created_at, expires_at, hash_ref_token, revoked_at) -> RefreshSession | None:
    with Session(engine) as session:
        ref_session = session.get(RefreshSession, session_id)
        if ref_session is None: return None
        
        ref_session.refresh_token_hash = hash_ref_token
        ref_session.expires_at = expires_at
        ref_session.created_at = created_at
        ref_session.revoked_at = revoked_at

        session.commit()
        return session.get(RefreshSession, session_id)
        


# ==============================================================
# ======================= USER =================================
def create_user(user_data: User) -> User:
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
            password=user_data.password,
            updated_at=user_data.updated_at,
            created_at=user_data.created_at,
            deleted_at=None,
            user_status=UserStatus.ACTIVE # by default
        )

        session.add(user)
        session.commit()
    return user # it error -> it throws exception

def get_user(id: str) -> User | None:
    with Session(engine) as session:
        result = session.get(User, id)
        return result

def get_user_by_email(inputted_email: str) -> User | None:
    with Session(engine) as session:
        return session.query(User).filter_by(email=inputted_email).first()

def get_user_by_nickname(inputted_nickname: str) -> User | None:
    with Session(engine) as session:
        return session.query(User).filter_by(nickname=inputted_nickname).first()
        

def get_users() -> list[User]:
    with Session(engine) as session:
        query = select(User)
        return session.scalars(query).all()

def update_user(id: str, new_info: dict) -> User | None:
    with Session(engine) as session:
        user = session.get(User, id)

        if user is None:
            return None
        
        for field, value in new_info.items():
            setattr(user, field, value)
            
        user.updated_at = datetime.now()
        session.commit()
        session.refresh(user)
        return user


def delete_user(id: str) -> bool:
    with Session(engine) as session:
        # more layer safety:
        user = session.get(User, id)
        if user is None:
            return False
        
        user.deleted_at = datetime.now(timezone.utc)
        user.user_status = UserStatus.DELETED
        session.commit()
        return True 
        
def delete_all_users() -> int:
    with Session(engine) as session:

        result = session.execute(
            update(User)
            .where(User.deleted_at.is_(None))
            .values(
                deleted_at=datetime.now(timezone.utc),
                user_status=UserStatus.DELETED
            )
        )
        session.commit()
        return result.rowcount


# ==============================================================
# ======================= TICKETS ==============================

def create_ticket(ticket_data: Ticket) -> Ticket:
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
        return ticket

def get_ticket(id: str) -> Ticket | None:
    with Session(engine) as session:
        result = session.get(Ticket, id)
        return result
    
def get_tickets() -> list[Ticket]:
    with Session(engine) as session:
        query = select(Ticket)
        return session.scalars(query).all()

def update_ticket(id: str, new_info: dict) -> Ticket | None:
    with Session(engine) as session:
        ticket = session.get(Ticket, id)

        if ticket is None:
            return None

        for field, value in new_info.items():
            setattr(ticket, field, value)
        ticket.updated_at = datetime.now(timezone.utc)

        session.commit()
        session.refresh(ticket)
        return ticket


def delete_ticket(id: str) -> bool:
    with Session(engine) as session:
        ticket = session.get(Ticket, id)
        if ticket is None:
            return False
        
        ticket.deleted_at = datetime.now(timezone.utc)
        ticket.updated_at = datetime.now(timezone.utc)
        session.commit()
        return True

def delete_all_tickets() -> int:
    with Session(engine) as session:
        result = session.execute(
            update(Ticket)
            .where(Ticket.deleted_at.is_(None))
            .values(
                deleted_at=datetime.now(timezone.utc),
                updated_at = datetime.now(timezone.utc)
            ))

        session.commit()
        return result.rowcount

def claim_ticket(ticket_id: str, assigned_id: str) -> Ticket | None:
    with Session(engine) as session:
        ticket = session.get(Ticket, ticket_id)
        if ticket is None:
            return None

        ticket.assigned_agent_id = assigned_id
        ticket.status = Status.IN_PROGRESS
        ticket.updated_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(ticket)
        return ticket
