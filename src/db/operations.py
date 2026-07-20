from dataclasses import dataclass
from sqlalchemy.orm import Session
from .engine import engine
from .models import AgentProfile, Ticket, User, RefreshSession, UserStatus, Event, Comment, AnalysisResult
from sqlalchemy import Row, func, select, delete, update
from datetime import datetime, timezone
from src.constants import (
    AvailabilityStatus,
    EntityType,
    EventType,
    Role,
    StartWorkOutcome,
    Status,
    TicketRoutingOutcome,
    DEFAULT_SORT_ORDER,
    DEFAULT_PAGE_LIMIT,
    DEFAULT_SORT_BY,
    _audit_json,
    apply_sort_order,
    generate_id,
    Priority,
)
from src.exceptions.domain import AgentHasActiveTicketsError, AgentProfileNotFoundError


ACTIVE_TICKET_STATUSES = (
    Status.OPEN,
    Status.IN_PROGRESS,
    Status.PENDING,
    Status.ON_HOLD,
    Status.REOPENED,
)


@dataclass(frozen=True)
class TicketRoutingResult:
    outcome: TicketRoutingOutcome
    ticket_id: str
    assigned_agent_id: str | None = None


@dataclass(frozen=True)
class StartWorkResult:
    outcome: StartWorkOutcome
    ticket: Ticket | None = None


# ==============================================================
# ======================= SYSTEM ===============================
def create_refresh_session(old_refresh_session: RefreshSession, event_data: Event | None = None) -> RefreshSession | None:
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
        if event_data is not None:
            session.add(_event_from_data(event_data))
        session.commit()
    return refresh_session

def get_refresh_session_by_id(refresh_session_id: str) -> RefreshSession | None:
    with Session(engine) as session:
        return session.query(RefreshSession).filter_by(id=refresh_session_id).first()

def get_refresh_session_by_hash_refresh_token(hash_token: str) -> RefreshSession | None:
    with Session(engine) as session:
        return session.query(RefreshSession).filter_by(refresh_token_hash=hash_token).first()
    
def revoke_refresh_session(session_id: str, revoked_at: datetime | None = None, event_data: Event | None = None) -> bool:
    with Session(engine) as session:
        with session.begin():
            refresh_session = session.get(RefreshSession, session_id)
            if refresh_session is None:
                return False
            refresh_session.revoked_at = revoked_at or datetime.now(timezone.utc)
            if event_data is not None:
                session.add(_event_from_data(event_data))

    
    return True

def rotate_refresh_session(session_id, current_hash, created_at, expires_at, hash_ref_token, revoked_at, event_data: Event | None = None) -> RefreshSession | None:
    with Session(engine) as session:
        with session.begin():
            result = session.execute(
                update(RefreshSession)
                .where(
                    RefreshSession.id == session_id,
                    RefreshSession.refresh_token_hash == current_hash,
                    RefreshSession.revoked_at.is_(None),
                    RefreshSession.expires_at > created_at,
                )
                .values(
                    refresh_token_hash=hash_ref_token,
                    expires_at=expires_at,
                    created_at=created_at,
                    revoked_at=revoked_at,
                )
            )
            if result.rowcount != 1:
                return None
            if event_data is not None:
                session.add(_event_from_data(event_data))

        return session.get(RefreshSession, session_id)
        


# ==============================================================
# ======================= USER =================================
def create_user(user_data: User, event_data: Event | None = None) -> User:
    with Session(engine) as session:
        with session.begin():
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
            if event_data is not None:
                session.add(_event_from_data(event_data))
    return user # it error -> it throws exception


def create_initial_superadmin(user_data: User, event_data: Event) -> bool:
    with Session(engine) as session:
        try:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")

            if session.scalar(select(User.id).limit(1)) is not None:
                session.rollback()
                return False

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
                user_status=UserStatus.ACTIVE,
            )
            session.add(user)
            session.flush()
            session.add(_event_from_data(event_data))
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise

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
        

def get_users(
            limit: int | None = None,
            offset: int = 0,
            sort_by: str = DEFAULT_SORT_BY,
            sort_order: str = DEFAULT_SORT_ORDER) -> list[User]:
    
    sort_columns = {
        "created_at": User.created_at,
        "user_status": User.user_status,
        "role": User.role,
        "first_name": User.first_name,
        "last_name": User.last_name,
    }
    with Session(engine) as session:
        sort_col = sort_columns[sort_by]

        order_exp = apply_sort_order(sort_col, sort_order)
        
        query = select(User).order_by(order_exp).offset(offset)
        if limit is not None:
            query = query.limit(limit)
            
        return session.scalars(query).all()


def get_agent_profile(user_id: str) -> AgentProfile | None:
    with Session(engine) as session:
        return session.get(AgentProfile, user_id)


def count_active_assigned_tickets(agent_user_id: str) -> int:
    with Session(engine) as session:
        return _count_active_assigned_tickets(session, agent_user_id)


def _get_least_loaded_eligible_agent(
    session: Session,
    *,
    lock_for_update: bool = False,
) -> User | None:
    #Department, skill, tag, and performance ranking deliberately do not belong in this first routing query.
    active_ticket_count = (
        select(func.count(Ticket.id))
        .where(
            Ticket.assigned_agent_id == User.id,
            Ticket.deleted_at.is_(None),
            Ticket.status.in_(ACTIVE_TICKET_STATUSES),
        )
        .correlate(User)
        .scalar_subquery()
    )
    statement = (
        select(User)
        .join(AgentProfile, AgentProfile.user_id == User.id)
        .where(
            User.role == Role.AGENT,
            User.user_status == UserStatus.ACTIVE,
            User.deleted_at.is_(None),
            AgentProfile.availability_status == AvailabilityStatus.AVAILABLE,
            active_ticket_count < AgentProfile.max_active_tickets,
        )
        .order_by(
            active_ticket_count.asc(),
            AgentProfile.last_assigned_at.asc().nulls_first(),
            User.id.asc(),
        )
        .limit(1)
    )

    if lock_for_update:
        statement = statement.with_for_update()

    return session.scalar(statement)


def get_least_loaded_eligible_agent() -> User | None:
    with Session(engine) as session:
        return _get_least_loaded_eligible_agent(session)


def update_agent_profile(
    user_id: str,
    new_info: dict,
    event_data: Event,
) -> AgentProfile | None:
    """Save the profile change and its audit event atomically."""

    with Session(engine) as session:
        with session.begin():
            profile = session.get(AgentProfile, user_id)
            if profile is None:
                return None

            for field, value in new_info.items():
                setattr(profile, field, value)
            session.add(_event_from_data(event_data))

        session.refresh(profile)
        return profile


def _count_active_assigned_tickets(session: Session, agent_user_id: str) -> int:
    statement = (
        select(func.count())
        .select_from(Ticket)
        .where(
            Ticket.assigned_agent_id == agent_user_id,
            Ticket.deleted_at.is_(None),
            Ticket.status.in_(ACTIVE_TICKET_STATUSES),
        )
    )
    return session.scalar(statement) or 0


def _apply_agent_role_lifecycle(
    session: Session,
    user: User,
    new_role: Role,
    now: datetime,
) -> None:
    old_role = user.role

    if old_role == Role.USER and new_role == Role.AGENT:
        profile = session.get(AgentProfile, user.id)
        if profile is None:
            profile = AgentProfile(
                user_id=user.id,
                availability_status=AvailabilityStatus.OFFLINE,
                availability_reason="profile_setup_required",
                availability_note=None,
                unavailable_until=None,
                max_active_tickets=0,
                last_assigned_at=None,
                department_id=None,
                created_at=now,
                updated_at=now,
            )
            session.add(profile)
        else:
            profile.availability_status = AvailabilityStatus.OFFLINE
            profile.availability_reason = "profile_setup_required"
            profile.updated_at = now

    if old_role == Role.AGENT and new_role == Role.MANAGER:
        active_ticket_count = _count_active_assigned_tickets(session, user.id)
        if active_ticket_count:
            raise AgentHasActiveTicketsError(active_ticket_count)

        profile = session.get(AgentProfile, user.id)
        if profile is None:
            # Supports agents created before AgentProfile existed.
            profile = AgentProfile(
                user_id=user.id,
                availability_status=AvailabilityStatus.OFFLINE,
                availability_reason="role_changed_to_manager",
                availability_note=None,
                unavailable_until=None,
                max_active_tickets=0,
                last_assigned_at=None,
                department_id=None,
                created_at=now,
                updated_at=now,
            )
            session.add(profile)
        else:
            profile.availability_status = AvailabilityStatus.OFFLINE
            profile.availability_reason = "role_changed_to_manager"
            profile.unavailable_until = None
            profile.updated_at = now

def update_user(id: str, new_info: dict, event_data: Event | None = None) -> User | None:
    with Session(engine) as session:
        with session.begin():
            user = session.get(User, id)

            if user is None:
                return None

            now = datetime.now(timezone.utc)
            new_role = new_info.get("role")
            if new_role is not None and new_role != user.role:
                _apply_agent_role_lifecycle(session, user, new_role, now)

            for field, value in new_info.items():
                setattr(user, field, value)
            user.updated_at = now
            if event_data is not None:
                session.add(_event_from_data(event_data))

        
        session.refresh(user)

        return user


def delete_user(id: str, delete_info: dict, event_data: Event | None = None) -> bool:
    with Session(engine) as session:
        with session.begin():
            user = session.get(User, id)
            if user is None:
                return False

            for field, value in delete_info.items():
                setattr(user, field, value)
            if event_data is not None:
                session.add(_event_from_data(event_data))

        return True 
        
def delete_all_users(event_data: list[Event] | None = None) -> int:
    with Session(engine) as session:
        with session.begin():
            result = session.execute(
                update(User)
                .where(User.deleted_at.is_(None))
                .values(
                    deleted_at=datetime.now(timezone.utc),
                    user_status=UserStatus.DELETED
                )
            )
            for event in event_data or []:
                session.add(_event_from_data(event))

        return result.rowcount


# ==============================================================
# ======================= TICKETS ==============================

def create_ticket(ticket_data: Ticket, event_data: Event | None = None) -> Ticket:
    with Session(engine) as session:
        with session.begin():
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
            if event_data is not None:
                session.add(_event_from_data(event_data))

        session.refresh(ticket)
        return ticket

def get_ticket(id: str) -> Ticket | None:
    with Session(engine) as session:
        result = session.get(Ticket, id)
        return result
            # limit: int,
        # offset: int,
        # sort_by: str,
        # sort_order: str,
        # priority: constants.Priority | None
def get_tickets(
        limit: int | None = None,
        offset: int = 0,
        sort_by: str = DEFAULT_SORT_BY,
        sort_order: str = DEFAULT_SORT_ORDER,
        priority: Priority | None = None,
        status: Status | None = None
) -> list[Ticket]:
    with Session(engine) as session: 
        sort_columns = {
            'created_at': Ticket.created_at,
            'updated_at': Ticket.updated_at,
            'status': Ticket.status,
            'priority': Ticket.priority,
        }
        sort_col = sort_columns[sort_by]
        order_exp = apply_sort_order(sort_col, sort_order)

        query = select(Ticket)
        if priority:
            query = query.where(Ticket.priority == priority)
        if status:
            query = query.where(Ticket.status == status)

        query = query.order_by(order_exp).offset(offset)
        if limit is not None:
            query = query.limit(limit)

        return session.scalars(query).all()


def get_waiting_ticket_ids(limit: int) -> list[str]:
    """Return one bounded, deterministic reconciliation page.

    The session is closed before callers enqueue work, so Redis operations never
    extend the lifetime of this database read transaction.
    """
    if limit <= 0:
        raise ValueError("limit must be greater than zero")

    statement = (
        select(Ticket.id)
        .where(
            Ticket.deleted_at.is_(None),
            Ticket.status == Status.NEW,
            Ticket.assigned_agent_id.is_(None),
        )
        .order_by(Ticket.created_at.asc(), Ticket.id.asc())
        .limit(limit)
    )
    with Session(engine) as session:
        return list(session.scalars(statement).all())


def update_ticket(id: str, new_info: dict, event_data: Event | None = None) -> Ticket | None:
    with Session(engine) as session:
        with session.begin():
            ticket = session.get(Ticket, id)

            if ticket is None:
                return None

            old_assignee_id = ticket.assigned_agent_id
            for field, value in new_info.items():
                setattr(ticket, field, value)
            now = datetime.now(timezone.utc)
            ticket.updated_at = now
            new_assignee_id = ticket.assigned_agent_id
            if new_assignee_id is not None and new_assignee_id != old_assignee_id:
                _record_agent_received_ticket(session, new_assignee_id, now)
            if event_data is not None:
                session.add(_event_from_data(event_data))

        session.refresh(ticket)
        return ticket


def delete_ticket(id: str, delete_info: dict, event_data: Event | None = None) -> bool:
    with Session(engine) as session:
        with session.begin():
            ticket = session.get(Ticket, id)
            if ticket is None:
                return False

            for field, value in delete_info.items():
                setattr(ticket, field, value)
            if event_data is not None:
                session.add(_event_from_data(event_data))

        return True

def delete_all_tickets(event_data: list[Event] | None = None) -> int:
    with Session(engine) as session:
        with session.begin():
            result = session.execute(
                update(Ticket)
                .where(Ticket.deleted_at.is_(None))
                .values(
                    deleted_at=datetime.now(timezone.utc),
                    updated_at = datetime.now(timezone.utc)
                ))
            for event in event_data or []:
                session.add(_event_from_data(event))
        
        return result.rowcount

def claim_ticket(ticket_id: str, assigned_id: str, event_data: Event | None = None) -> Ticket | None:
    with Session(engine) as session:
        with session.begin():
            agent = session.get(User, assigned_id)
            if agent is None: return None

            now = datetime.now(timezone.utc)
            result = session.execute(
                update(Ticket)
                .where(
                    Ticket.id == ticket_id,
                    Ticket.assigned_agent_id.is_(None),
                    Ticket.status == Status.NEW,
                    Ticket.deleted_at.is_(None),
                )
                .values(
                    assigned_agent_id=assigned_id,
                    status=Status.OPEN,
                    updated_at=now,
                )
            )
            if result.rowcount != 1:
                return None

            if event_data is not None:
                session.add(_event_from_data(event_data))

            _record_agent_received_ticket(session, assigned_id, now)

            ticket = session.get(Ticket, ticket_id)

        session.refresh(ticket)
        return ticket


def try_route_ticket(ticket_id: str) -> TicketRoutingResult:
 
    with Session(engine) as session:
        try:
            # SQLite ignores SELECT ... FOR UPDATE. BEGIN IMMEDIATE makes
            # competing routing writers wait before either one reads the
            # ticket. Databases with row-lock support use FOR UPDATE below.
            if session.get_bind().dialect.name == "sqlite":
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            else:
                session.begin()

            ticket = session.scalar(
                select(Ticket)
                .where(Ticket.id == ticket_id)
                .with_for_update()
            )
            if (
                ticket is None
                or ticket.deleted_at is not None
                or ticket.status != Status.NEW
                or ticket.assigned_agent_id is not None
            ):
                session.commit()
                return TicketRoutingResult(
                    outcome=TicketRoutingOutcome.TICKET_NOT_ROUTABLE,
                    ticket_id=ticket_id,
                )

            agent = _get_least_loaded_eligible_agent(
                session,
                lock_for_update=True,
            )
            if agent is None:
                session.commit()
                return TicketRoutingResult(
                    outcome=TicketRoutingOutcome.NO_ELIGIBLE_AGENT,
                    ticket_id=ticket_id,
                )

            now = datetime.now(timezone.utc)
            ticket.assigned_agent_id = agent.id
            ticket.status = Status.OPEN
            ticket.updated_at = now
            _record_agent_received_ticket(session, agent.id, now)
            session.add(
                Event(
                    id=generate_id(),
                    entity_type=EntityType.TICKET,
                    entity_id=ticket.id,
                    # The ticket creator initiated the workflow. Metadata makes
                    # clear that the assignment itself was performed by routing.
                    actor_user_id=ticket.creator_user_id,
                    event_type=EventType.TICKET_ASSIGNED,
                    old_value=_audit_json(
                        {
                            "status": Status.NEW,
                            "assigned_agent_id": None,
                        }
                    ),
                    new_value=_audit_json(
                        {
                            "status": Status.OPEN,
                            "assigned_agent_id": agent.id,
                        }
                    ),
                    metadata_="source=automatic_router",
                    created_at=now,
                )
            )
            session.commit()
            return TicketRoutingResult(
                outcome=TicketRoutingOutcome.ASSIGNED,
                ticket_id=ticket.id,
                assigned_agent_id=agent.id,
            )
        except Exception:
            session.rollback()
            raise


def assign_ticket(ticket_id: str, assigned_agent_id:str, event_data: Event | None = None) -> Ticket | None:
    with Session(engine) as session:
        with session.begin():
            ticket = session.get(Ticket, ticket_id)
            if ticket is None:
                return None

            user = session.get(User, assigned_agent_id)
            if user is None: return None

            old_assignee_id = ticket.assigned_agent_id
            now = datetime.now(timezone.utc)
            ticket.assigned_agent_id = user.id
            ticket.status = Status.OPEN
            ticket.updated_at = now
            if user.id != old_assignee_id:
                _record_agent_received_ticket(session, user.id, now)
            if event_data is not None:
                session.add(_event_from_data(event_data))

        session.refresh(ticket)
        return ticket


def start_ticket_work(ticket_id: str, requester_id: str) -> StartWorkResult:
    """Atomically move the requester's assigned OPEN ticket to IN_PROGRESS."""
    with Session(engine) as session:
        try:
            # SQLite has no effective SELECT ... FOR UPDATE support. Acquiring
            # the write lock before reading gives the read/check/write sequence
            # the same single-writer boundary used by the routing operation.
            if session.get_bind().dialect.name == "sqlite":
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            else:
                session.begin()

            ticket = session.scalar(
                select(Ticket)
                .where(Ticket.id == ticket_id)
                .with_for_update()
            )
            if ticket is None:
                session.commit()
                return StartWorkResult(StartWorkOutcome.TICKET_NOT_FOUND)
            if ticket.deleted_at is not None:
                session.commit()
                return StartWorkResult(StartWorkOutcome.TICKET_DELETED)
            if ticket.assigned_agent_id is None:
                session.commit()
                return StartWorkResult(StartWorkOutcome.TICKET_UNASSIGNED)
            if ticket.assigned_agent_id != requester_id:
                session.commit()
                return StartWorkResult(
                    StartWorkOutcome.ASSIGNED_TO_ANOTHER_AGENT
                )
            if ticket.status == Status.IN_PROGRESS:
                session.commit()
                return StartWorkResult(
                    StartWorkOutcome.TICKET_ALREADY_STARTED
                )
            if ticket.status != Status.OPEN:
                session.commit()
                return StartWorkResult(StartWorkOutcome.TICKET_NOT_OPEN)

            now = datetime.now(timezone.utc)
            ticket.status = Status.IN_PROGRESS
            ticket.updated_at = now
            session.add(
                Event(
                    id=generate_id(),
                    entity_type=EntityType.TICKET,
                    entity_id=ticket.id,
                    actor_user_id=requester_id,
                    event_type=EventType.TICKET_STATUS_CHANGED,
                    old_value=_audit_json({"status": Status.OPEN}),
                    new_value=_audit_json({"status": Status.IN_PROGRESS}),
                    metadata_=None,
                    created_at=now,
                )
            )
            session.commit()
            session.refresh(ticket)
            return StartWorkResult(StartWorkOutcome.STARTED, ticket)
        except Exception:
            session.rollback()
            raise


def _record_agent_received_ticket(
    session: Session,
    agent_user_id: str,
    assigned_at: datetime,
) -> None:
    profile = session.get(AgentProfile, agent_user_id)
    if profile is None:
        raise AgentProfileNotFoundError()
    profile.last_assigned_at = assigned_at
    profile.updated_at = assigned_at


# ==============================================================
# ===================== COMMENTS ===============================
def _event_from_data(event_data: Event) -> Event:
    return Event(
        id=event_data.id,
        entity_type=event_data.entity_type,
        entity_id=event_data.entity_id,
        actor_user_id=event_data.actor_user_id,
        event_type=event_data.event_type,
        old_value=event_data.old_value,
        new_value=event_data.new_value,
        metadata_=event_data.metadata,
        created_at=event_data.created_at,
        batch_id=event_data.batch_id
    )


def create_comment(comment_data: Comment) -> Comment | None:
    with Session(engine) as session:
        with session.begin():
            comment = Comment(
                id = comment_data.id,
                ticket_id = comment_data.ticket_id,
                author_user_id = comment_data.author_user_id,
                body = comment_data.body,
                visibility = comment_data.visibility,
                edited_at = comment_data.edited_at,
                created_at = comment_data.created_at,
                updated_at = comment_data.updated_at,
                deleted_at = comment_data.deleted_at,
                deleted_by_user_id = comment_data.deleted_by_user_id,
                parent_comment_id = comment_data.parent_comment_id,
                attachments_count = comment_data.attachments_count,
                source = comment_data.source
            )

            session.add(comment)

        session.refresh(comment)
        return comment

def create_comment_with_event(comment_data: Comment, event_data: Event) -> Comment | None:
    with Session(engine) as session:
        with session.begin():
            comment = Comment(
                id = comment_data.id,
                ticket_id = comment_data.ticket_id,
                author_user_id = comment_data.author_user_id,
                body = comment_data.body,
                visibility = comment_data.visibility,
                edited_at = comment_data.edited_at,
                created_at = comment_data.created_at,
                updated_at = comment_data.updated_at,
                deleted_at = comment_data.deleted_at,
                deleted_by_user_id = comment_data.deleted_by_user_id,
                parent_comment_id = comment_data.parent_comment_id,
                attachments_count = comment_data.attachments_count,
                source = comment_data.source
            )
            session.add(comment)
            session.add(_event_from_data(event_data))

        session.refresh(comment)
        return comment

def get_comment(comment_id: str) -> Comment | None:
    with Session(engine) as session:
        with session.begin():
            comment = session.get(Comment, comment_id)
            return comment


def get_comments(
                ticket_id: str | None = None,
                limit: int | None = None,
                offset: int = 0,
                sort_by: str = DEFAULT_SORT_BY,
                sort_order: str = DEFAULT_SORT_ORDER) -> list[Comment]:
    with Session(engine) as session:
        with session.begin():
            sort_columns = {
                "created_at": Comment.created_at,
                "updated_at": Comment.updated_at,
            }
            sort_col = sort_columns[sort_by]

            order_exp = apply_sort_order(sort_col, sort_order)

            query = select(Comment).order_by(order_exp).offset(offset)
            if limit:
                query = query.limit(limit)
            
            if ticket_id is not None:
                query = query.where(Comment.ticket_id == ticket_id)
            return session.scalars(query).all()


def update_comment(comment_id: str, new_info: dict) -> Comment | None:
    with Session(engine) as session:
        with session.begin():
            comment = session.get(Comment, comment_id)
            if comment is None:
                return None

            for field, value in new_info.items():
                setattr(comment, field, value)
            now = datetime.now(timezone.utc)
            comment.updated_at = now
            if "body" in new_info:
                comment.edited_at = now

        session.refresh(comment)
        return comment

def update_comment_with_event(comment_id: str, new_info: dict, event_data: Event) -> Comment | None:
    with Session(engine) as session:
        with session.begin():
            comment = session.get(Comment, comment_id)
            if comment is None:
                return None

            for field, value in new_info.items():
                setattr(comment, field, value)
            now = datetime.now(timezone.utc)
            comment.updated_at = now
            if "body" in new_info:
                comment.edited_at = now

            session.add(_event_from_data(event_data))

        session.refresh(comment)
        return comment

def delete_comment(comment_id: str, delete_info: dict) -> bool:
    with Session(engine) as session:
        with session.begin():
            comment = session.get(Comment, comment_id)
            if comment is None:
                return False

            for field, value in delete_info.items():
                setattr(comment, field, value)

        return True

def delete_comment_with_event(comment_id: str, delete_info: dict, event_data: Event) -> bool:
    with Session(engine) as session:
        with session.begin():
            comment = session.get(Comment, comment_id)
            if comment is None:
                return False

            for field, value in delete_info.items():
                setattr(comment, field, value)

            session.add(_event_from_data(event_data))

        return True


# ==============================================================
# ======================= EVENTS ===============================

def create_event(event: Event) -> bool:
    with Session(engine) as session:
        with session.begin():
            if event is None: return False
            session.add(_event_from_data(event))
    return True


# ================================================================
# ======================= ANALYSIS ===============================
def create_analysis_result(analysis: AnalysisResult) -> bool:
    with Session(engine) as session:
        with session.begin():
            if analysis is None: return False
            session.add(analysis)
    return True

def get_analysis_result_by_job(job_id: str) -> AnalysisResult | None:
    with Session(engine) as session:
        with session.begin():
            if job_id is None: return False

            return session.query(AnalysisResult).filter_by(job_id=job_id).first()

def get_analysis_results_by_ticket(ticket_id: str) -> list[AnalysisResult] | None:
    with Session(engine) as session: 
        query = select(AnalysisResult)
        query = query.where(AnalysisResult.ticket_id == ticket_id)

        return session.scalars(query).all()
