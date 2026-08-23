from dataclasses import dataclass
from collections.abc import Callable
from sqlalchemy.orm import Session
from .engine import engine
from .models import (
    AgentProfile,
    Attachment,
    AnalysisResult,
    AISetting,
    Comment,
    Department,
    Event,
    RefreshSession,
    Skill,
    Ticket,
    TicketLink,
    Notification,
    User,
    UserStatus,
    agent_skills,
    ticket_skills,
)
from sqlalchemy import Row, and_, func, or_, select, delete, update
from datetime import datetime, timezone
from src.constants import (
    ActorType,
    AnalysisStatus,
    AvailabilityStatus,
    EntityType,
    EventType,
    Role,
    StartWorkOutcome,
    Status,
    TicketRoutingOutcome,
    Visibility,
    calculate_sla_due_at,
    utc_now,
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


@dataclass(frozen=True)
class AnalysisReservation:
    result: AnalysisResult
    created: bool


def _new_global_ai_setting(now: datetime) -> AISetting:
    return AISetting(
        id="global",
        provider="fake",
        model="deterministic-fake-v1",
        version=1,
        updated_by_user_id=None,
        created_at=now,
        updated_at=now,
    )


def get_ai_setting() -> AISetting:
    """Read the singleton without opening a write transaction."""
    with Session(engine) as session:
        setting = session.get(AISetting, "global")
        if setting is not None:
            return setting
    # Test fixtures may create metadata directly instead of running create_db.
    # Return the documented default without nesting a write inside an active
    # ticket-reservation transaction; normal startup seeds the durable row.
    return _new_global_ai_setting(utc_now())


def update_ai_setting(
    *,
    provider: str,
    model: str,
    expected_version: int,
    updated_by_user_id: str,
    now: datetime,
) -> AISetting | None:
    """Update the setting and audit event atomically, or return a conflict."""
    with Session(engine, expire_on_commit=False) as session:
        with session.begin():
            statement = select(AISetting).where(AISetting.id == "global")
            if session.get_bind().dialect.name != "sqlite":
                statement = statement.with_for_update()
            setting = session.scalar(statement)
            if setting is None:
                setting = _new_global_ai_setting(now)
                session.add(setting)
                session.flush()
            if setting.version != expected_version:
                return None

            old_value = _audit_json({
                "provider": setting.provider,
                "model": setting.model,
                "version": setting.version,
            })
            setting.provider = provider
            setting.model = model
            setting.version += 1
            setting.updated_by_user_id = updated_by_user_id
            setting.updated_at = now
            session.add(_event_from_data(Event(
                id=generate_id(),
                entity_type=EntityType.AI_SETTINGS,
                entity_id="global",
                actor_type=ActorType.HUMAN,
                actor_user_id=updated_by_user_id,
                event_type=EventType.AI_SETTINGS_UPDATED,
                old_value=old_value,
                new_value=_audit_json({
                    "provider": provider,
                    "model": model,
                    "version": setting.version,
                }),
                created_at=now,
            )))
            session.flush()
            return setting


def record_ai_provider_test(
    *,
    provider: str,
    model: str,
    actor_user_id: str,
    ok: bool,
    error_code: str | None,
    now: datetime,
) -> bool:
    """Write safe provider-test metadata without prompt or output content."""
    with Session(engine) as session:
        with session.begin():
            session.add(_event_from_data(Event(
                id=generate_id(),
                entity_type=EntityType.AI_SETTINGS,
                entity_id="global",
                actor_type=ActorType.HUMAN,
                actor_user_id=actor_user_id,
                event_type=EventType.AI_PROVIDER_TESTED,
                old_value=None,
                new_value=_audit_json({
                    "provider": provider,
                    "model": model,
                    "ok": ok,
                    "error_code": error_code,
                }),
                created_at=now,
            )))
    return True


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
            # The creation event references this same new user as its actor.
            # Flush the parent row first because no ORM relationship tells
            # SQLAlchemy how to order these otherwise independent objects.
            session.flush()
            if event_data is not None:
                session.add(_event_from_data(event_data))
    return user # it error -> it throws exception


def create_initial_superadmin(user_data: User, event_data: Event) -> bool:
    with Session(engine) as session:
        try:
            # SQLite: BEGIN IMMEDIATE serializes writers before the
            # empty-table check. PostgreSQL: SELECT ... FOR UPDATE cannot
            # lock rows that do not exist yet, so a brief table lock gives
            # this one-time bootstrap the same single-writer boundary
            # (SHARE ROW EXCLUSIVE conflicts with itself; plain reads are
            # unaffected).
            if session.get_bind().dialect.name == "sqlite":
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            else:
                session.begin()
                session.connection().exec_driver_sql(
                    "LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"
                )

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


def get_active_user_ids_by_roles(roles: set[Role]) -> list[str]:
    """Return notification recipients without exposing user records."""
    if not roles:
        return []
    with Session(engine) as session:
        return list(session.scalars(
            select(User.id).where(
                User.role.in_(roles),
                User.user_status == UserStatus.ACTIVE,
                User.deleted_at.is_(None),
            )
        ).all())


def count_active_superadmins() -> int:
    with Session(engine) as session:
        return session.scalar(
            select(func.count(User.id)).where(
                User.role == Role.SUPER_ADMIN,
                User.user_status == UserStatus.ACTIVE,
                User.deleted_at.is_(None),
            )
        ) or 0


def count_active_administrators() -> int:
    with Session(engine) as session:
        return session.scalar(
            select(func.count(User.id)).where(
                User.role.in_((Role.ADMIN, Role.SUPER_ADMIN)),
                User.user_status == UserStatus.ACTIVE,
                User.deleted_at.is_(None),
            )
        ) or 0


def create_notification(
    recipient_user_id: str,
    notification_type: str,
    message: str,
    *,
    ticket_id: str | None = None,
    idempotency_key: str | None = None,
) -> Notification:
    with Session(engine) as session:
        with session.begin():
            if idempotency_key:
                existing = session.scalar(
                    select(Notification).where(
                        Notification.idempotency_key == idempotency_key
                    )
                )
                if existing is not None:
                    return existing
            notification = Notification(
                id=generate_id(),
                recipient_user_id=recipient_user_id,
                notification_type=notification_type,
                ticket_id=ticket_id,
                message=message,
                created_at=utc_now(),
                read_at=None,
                idempotency_key=idempotency_key,
            )
            session.add(notification)
        session.refresh(notification)
        return notification


def list_notifications(
    recipient_user_id: str,
    limit: int,
    offset: int,
    *,
    unread_only: bool = False,
) -> list[Notification]:
    with Session(engine) as session:
        statement = select(Notification).where(
            Notification.recipient_user_id == recipient_user_id
        )
        if unread_only:
            statement = statement.where(Notification.read_at.is_(None))
        statement = (
            statement.order_by(
                Notification.created_at.desc(), Notification.id.desc()
            )
            .offset(offset)
            .limit(limit)
        )
        return list(session.scalars(statement).all())


def count_unread_notifications(recipient_user_id: str) -> int:
    with Session(engine) as session:
        return session.scalar(
            select(func.count(Notification.id)).where(
                Notification.recipient_user_id == recipient_user_id,
                Notification.read_at.is_(None),
            )
        ) or 0


def mark_notification_read(
    notification_id: str,
    recipient_user_id: str,
) -> Notification | None:
    with Session(engine) as session:
        with session.begin():
            notification = session.scalar(
                select(Notification).where(
                    Notification.id == notification_id,
                    Notification.recipient_user_id == recipient_user_id,
                )
            )
            if notification is None:
                return None
            notification.read_at = utc_now()
        session.refresh(notification)
        return notification


def mark_all_notifications_read(recipient_user_id: str) -> int:
    with Session(engine) as session:
        with session.begin():
            result = session.execute(
                update(Notification)
                .where(
                    Notification.recipient_user_id == recipient_user_id,
                    Notification.read_at.is_(None),
                )
                .values(read_at=utc_now())
            )
        return result.rowcount

def get_user_by_email(inputted_email: str) -> User | None:
    with Session(engine) as session:
        return session.query(User).filter_by(email=inputted_email).first()

def get_user_by_nickname(inputted_nickname: str) -> User | None:
    with Session(engine) as session:
        return session.query(User).filter_by(nickname=inputted_nickname).first()


def get_routing_catalog_record(model, record_id: str, *, include_archived: bool = False):
    with Session(engine) as session:
        record = session.get(model, record_id)
        if record is None or (record.deleted_at is not None and not include_archived):
            return None
        return record


def list_routing_catalog_records(model, *, include_archived: bool = False) -> list:
    statement = select(model)
    if not include_archived:
        statement = statement.where(model.deleted_at.is_(None))
    statement = statement.order_by(model.normalized_name.asc(), model.id.asc())
    with Session(engine) as session:
        return list(session.scalars(statement).all())


def create_routing_catalog_record(record, event_data: Event):
    with Session(engine) as session:
        with session.begin():
            session.add(record)
            session.flush()
            session.add(_event_from_data(event_data))
        session.refresh(record)
        return record


def update_routing_catalog_record(model, record_id: str, new_info: dict, event_data: Event):
    with Session(engine) as session:
        with session.begin():
            record = session.get(model, record_id)
            if record is None:
                return None
            for field, value in new_info.items():
                setattr(record, field, value)
            session.add(_event_from_data(event_data))
        session.refresh(record)
        return record


def active_routing_catalog_selection(
    department_id: str | None,
    skill_ids: list[str],
) -> tuple[Department | None, list[Skill]]:
    with Session(engine) as session:
        department = session.get(Department, department_id) if department_id else None
        if department is not None and department.deleted_at is not None:
            department = None
        skills = []
        if skill_ids:
            skills = list(session.scalars(
                select(Skill).where(
                    Skill.id.in_(skill_ids),
                    Skill.deleted_at.is_(None),
                )
            ).all())
        return department, skills
        

def get_users(
            limit: int | None = None,
            offset: int = 0,
            sort_by: str = DEFAULT_SORT_BY,
            sort_order: str = DEFAULT_SORT_ORDER,
            *,
            role: Role | None = None,
            user_status: UserStatus | None = None,
            search: str | None = None,
            ) -> list[User]:
    
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
        
        query = select(User)
        if role:
            query = query.where(User.role == role)
        if user_status:
            query = query.where(User.user_status == user_status)
        if search and search.strip():
            pattern = f"%{search.strip()}%"
            query = query.where(
                or_(
                    User.id == search.strip(),
                    User.nickname.ilike(pattern),
                    User.first_name.ilike(pattern),
                    User.last_name.ilike(pattern),
                    User.email.ilike(pattern),
                )
            )
        query = query.order_by(order_exp, User.id.asc()).offset(offset)
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
    ticket: Ticket,
    *,
    lock_for_update: bool = False,
) -> User | None:
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
    matching_skill_count = (
        select(func.count(agent_skills.c.skill_id))
        .select_from(
            agent_skills.join(
                ticket_skills,
                ticket_skills.c.skill_id == agent_skills.c.skill_id,
            ).join(Skill, Skill.id == agent_skills.c.skill_id)
        )
        .where(
            agent_skills.c.agent_user_id == User.id,
            ticket_skills.c.ticket_id == ticket.id,
            Skill.deleted_at.is_(None),
        )
        .correlate(User)
        .scalar_subquery()
    )
    statement = (
        select(User)
        .join(AgentProfile, AgentProfile.user_id == User.id)
        .join(Department, Department.id == AgentProfile.department_id)
        .where(
            User.role == Role.AGENT,
            User.user_status == UserStatus.ACTIVE,
            User.deleted_at.is_(None),
            AgentProfile.availability_status == AvailabilityStatus.AVAILABLE,
            AgentProfile.department_id == ticket.department_id,
            Department.deleted_at.is_(None),
            active_ticket_count < AgentProfile.max_active_tickets,
        )
        .order_by(
            matching_skill_count.desc(),
            active_ticket_count.asc(),
            AgentProfile.last_assigned_at.asc().nulls_first(),
            User.id.asc(),
        )
        .limit(1)
    )

    if lock_for_update:
        statement = statement.with_for_update()

    return session.scalar(statement)


def get_least_loaded_eligible_agent(ticket_id: str) -> User | None:
    with Session(engine) as session:
        ticket = session.get(Ticket, ticket_id)
        if ticket is None:
            return None
        return _get_least_loaded_eligible_agent(session, ticket)


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

            skill_ids = new_info.pop("skill_ids", None)
            for field, value in new_info.items():
                setattr(profile, field, value)
            if skill_ids is not None:
                profile.skills = list(session.scalars(
                    select(Skill).where(Skill.id.in_(skill_ids))
                ).all()) if skill_ids else []
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


def create_staff_user(
    user: User,
    event_data: Event,
    *,
    max_active_tickets: int = 5,
    department_id: str | None = None,
    skill_ids: list[str] | None = None,
) -> User:
    with Session(engine) as session:
        with session.begin():
            session.add(user)
            if user.role is Role.AGENT:
                profile = AgentProfile(
                    user_id=user.id,
                    availability_status=AvailabilityStatus.OFFLINE,
                    availability_reason=None,
                    availability_note=None,
                    unavailable_until=None,
                    max_active_tickets=max_active_tickets,
                    last_assigned_at=None,
                    department_id=department_id,
                    created_at=user.created_at,
                    updated_at=user.updated_at,
                )
                if skill_ids:
                    profile.skills = list(
                        session.scalars(select(Skill).where(Skill.id.in_(skill_ids))).all()
                    )
                session.add(profile)
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

def create_ticket(
    ticket_data: Ticket,
    event_data: Event | None = None,
    skill_ids: list[str] | None = None,
) -> Ticket:
    with Session(engine) as session:
        with session.begin():
            ticket = Ticket(
                id=ticket_data.id,
                title=ticket_data.title,
                description=ticket_data.description,
                category=ticket_data.category,
                tags=ticket_data.tags,
                department_id=ticket_data.department_id,
                assigned_agent_id=ticket_data.assigned_agent_id,
                creator_user_id=ticket_data.creator_user_id,
                status=ticket_data.status,
                priority=ticket_data.priority,
                updated_at=ticket_data.updated_at,
                created_at=ticket_data.created_at,
                due_at=calculate_sla_due_at(
                    ticket_data.status,
                    ticket_data.created_at,
                    ticket_data.priority,
                ),
            )

            if skill_ids:
                ticket.requested_skills = list(session.scalars(
                    select(Skill).where(Skill.id.in_(skill_ids))
                ).all())

            session.add(ticket)
            if event_data is not None:
                session.add(_event_from_data(event_data))

        session.refresh(ticket)
        return ticket

def get_ticket(id: str) -> Ticket | None:
    with Session(engine) as session:
        result = session.get(Ticket, id)
        return result


def get_ticket_link(ticket_id: str, related_ticket_id: str) -> TicketLink | None:
    with Session(engine) as session:
        return session.scalar(
            select(TicketLink).where(
                TicketLink.ticket_id == ticket_id,
                TicketLink.related_ticket_id == related_ticket_id,
            )
        )


def create_ticket_link(link: TicketLink, event_data: Event) -> TicketLink:
    with Session(engine) as session:
        with session.begin():
            session.add(link)
            session.add(_event_from_data(event_data))
        session.refresh(link)
        return link


def get_ticket_links(ticket_id: str) -> list[tuple[TicketLink, Ticket]]:
    with Session(engine) as session:
        statement = (
            select(TicketLink, Ticket)
            .join(
                Ticket,
                or_(
                    and_(
                        TicketLink.ticket_id == ticket_id,
                        Ticket.id == TicketLink.related_ticket_id,
                    ),
                    and_(
                        TicketLink.related_ticket_id == ticket_id,
                        Ticket.id == TicketLink.ticket_id,
                    ),
                ),
            )
            .where(
                or_(
                    TicketLink.ticket_id == ticket_id,
                    TicketLink.related_ticket_id == ticket_id,
                )
            )
            .order_by(Ticket.created_at.desc(), Ticket.id.asc())
        )
        return list(session.execute(statement).all())


def delete_ticket_link(link_id: str, event_data: Event) -> bool:
    with Session(engine) as session:
        with session.begin():
            link = session.get(TicketLink, link_id)
            if link is None:
                return False
            session.delete(link)
            session.add(_event_from_data(event_data))
        return True
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
        status: Status | None = None,
        overdue: bool | None = None,
        now: datetime | None = None,
        *,
        requester_id: str | None = None,
        requester_role: Role | None = None,
        assigned_to_me: bool = False,
        department_id: str | None = None,
        assignee_id: str | None = None,
        category=None,
        tag=None,
        search: str | None = None,
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

        query = select(Ticket).where(Ticket.deleted_at.is_(None))
        if requester_role in (Role.ADMIN, Role.SUPER_ADMIN, Role.MANAGER, Role.AGENT_READONLY):
            pass
        elif requester_role is Role.AGENT:
            if assigned_to_me:
                query = query.where(Ticket.assigned_agent_id == requester_id)
            else:
                query = query.where(
                    or_(
                        Ticket.assigned_agent_id == requester_id,
                        and_(
                            Ticket.assigned_agent_id.is_(None),
                            Ticket.status == Status.NEW,
                        ),
                    )
                )
        elif requester_role is Role.USER:
            query = query.where(Ticket.creator_user_id == requester_id)
        else:
            query = query.where(Ticket.id == "__no_visible_ticket__")

        if department_id:
            query = query.where(Ticket.department_id == department_id)
        if assignee_id:
            query = query.where(Ticket.assigned_agent_id == assignee_id)
        if category:
            query = query.where(Ticket.category == category)
        if tag:
            # Tags are stored as a bounded JSON string for SQLite/PostgreSQL
            # compatibility. Searching for the quoted value avoids matching a
            # substring inside a different tag.
            tag_value = getattr(tag, "value", tag)
            query = query.where(Ticket.tags.like(f'%"{tag_value}"%'))
        if search:
            search_value = search.strip()
            if search_value:
                pattern = f"%{search_value}%"
                query = query.where(
                    or_(
                        Ticket.id == search_value,
                        Ticket.title.ilike(pattern),
                        Ticket.description.ilike(pattern),
                    )
                )
        if priority:
            query = query.where(Ticket.priority == priority)
        if status:
            query = query.where(Ticket.status == status)
        if overdue is not None:
            comparison_time = now or utc_now()
            if overdue:
                query = query.where(
                    Ticket.due_at.is_not(None),
                    Ticket.due_at < comparison_time,
                )
            else:
                query = query.where(
                    or_(
                        Ticket.due_at.is_(None),
                        Ticket.due_at >= comparison_time,
                    )
                )

        query = query.order_by(order_exp, Ticket.id.asc()).offset(offset)
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
            Ticket.department_id.is_not(None),
        )
        .order_by(Ticket.created_at.asc(), Ticket.id.asc())
        .limit(limit)
    )
    with Session(engine) as session:
        return list(session.scalars(statement).all())


def record_overdue_ticket_events(limit: int, now: datetime) -> list[str]:
    """Write one system-authored overdue event per ticket, atomically."""
    if limit <= 0:
        raise ValueError("limit must be greater than zero")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Overdue scan requires a timezone-aware timestamp")

    with Session(engine) as session:
        try:
            if session.get_bind().dialect.name == "sqlite":
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            else:
                session.begin()

            overdue_event_exists = (
                select(Event.id)
                .where(
                    Event.entity_type == EntityType.TICKET,
                    Event.entity_id == Ticket.id,
                    Event.event_type == EventType.TICKET_OVERDUE,
                )
                .correlate(Ticket)
                .exists()
            )
            statement = (
                select(Ticket)
                .where(
                    Ticket.deleted_at.is_(None),
                    Ticket.due_at.is_not(None),
                    Ticket.due_at < now,
                    ~overdue_event_exists,
                )
                .order_by(Ticket.due_at.asc(), Ticket.id.asc())
                .limit(limit)
            )
            if session.get_bind().dialect.name != "sqlite":
                statement = statement.with_for_update(skip_locked=True)

            tickets = list(session.scalars(statement).all())
            for ticket in tickets:
                session.add(Event(
                    id=generate_id(),
                    entity_type=EntityType.TICKET,
                    entity_id=ticket.id,
                    actor_type=ActorType.SYSTEM,
                    actor_user_id=None,
                    event_type=EventType.TICKET_OVERDUE,
                    old_value=None,
                    new_value=_audit_json({
                        "status": ticket.status,
                        "priority": ticket.priority,
                        "due_at": ticket.due_at,
                        "is_overdue": True,
                    }),
                    metadata_="source=overdue_scanner",
                    idempotency_key=f"ticket-overdue:{ticket.id}",
                    created_at=now,
                ))
            session.commit()
            return [ticket.id for ticket in tickets]
        except Exception:
            session.rollback()
            raise


def update_ticket(id: str, new_info: dict, event_data: Event | None = None) -> Ticket | None:
    with Session(engine) as session:
        with session.begin():
            ticket = session.get(Ticket, id)

            if ticket is None:
                return None

            old_assignee_id = ticket.assigned_agent_id
            now = event_data.created_at if event_data is not None else utc_now()
            skill_ids = new_info.pop("skill_ids", None)
            if "status" in new_info or "priority" in new_info:
                new_info = {
                    **new_info,
                    "due_at": calculate_sla_due_at(
                        new_info.get("status", ticket.status),
                        now,
                        new_info.get("priority", ticket.priority),
                    ),
                }
            for field, value in new_info.items():
                setattr(ticket, field, value)
            if skill_ids is not None:
                ticket.requested_skills = list(session.scalars(
                    select(Skill).where(Skill.id.in_(skill_ids))
                ).all()) if skill_ids else []
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

            now = event_data.created_at if event_data is not None else utc_now()
            ticket_priority = session.scalar(
                select(Ticket.priority).where(Ticket.id == ticket_id)
            )
            if ticket_priority is None:
                return None
            new_due_at = calculate_sla_due_at(Status.OPEN, now, ticket_priority)
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
                    due_at=new_due_at,
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
                ticket,
                lock_for_update=True,
            )
            if agent is None:
                session.commit()
                return TicketRoutingResult(
                    outcome=TicketRoutingOutcome.NO_ELIGIBLE_AGENT,
                    ticket_id=ticket_id,
                )

            now = utc_now()
            old_due_at = ticket.due_at
            new_due_at = calculate_sla_due_at(Status.OPEN, now, ticket.priority)
            ticket.assigned_agent_id = agent.id
            ticket.status = Status.OPEN
            ticket.due_at = new_due_at
            ticket.updated_at = now
            _record_agent_received_ticket(session, agent.id, now)
            session.add(
                Event(
                    id=generate_id(),
                    entity_type=EntityType.TICKET,
                    entity_id=ticket.id,
                    actor_type=ActorType.SYSTEM,
                    actor_user_id=None,
                    event_type=EventType.TICKET_ASSIGNED,
                    old_value=_audit_json(
                        {
                            "status": Status.NEW,
                            "assigned_agent_id": None,
                            "due_at": old_due_at,
                        }
                    ),
                    new_value=_audit_json(
                        {
                            "status": Status.OPEN,
                            "assigned_agent_id": agent.id,
                            "due_at": new_due_at,
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
            now = event_data.created_at if event_data is not None else utc_now()
            ticket.due_at = calculate_sla_due_at(Status.OPEN, now, ticket.priority)
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

            now = utc_now()
            old_due_at = ticket.due_at
            new_due_at = calculate_sla_due_at(
                Status.IN_PROGRESS,
                now,
                ticket.priority,
            )
            ticket.status = Status.IN_PROGRESS
            ticket.due_at = new_due_at
            ticket.updated_at = now
            session.add(
                Event(
                    id=generate_id(),
                    entity_type=EntityType.TICKET,
                    entity_id=ticket.id,
                    actor_user_id=requester_id,
                    event_type=EventType.TICKET_STATUS_CHANGED,
                    old_value=_audit_json({
                        "status": Status.OPEN,
                        "due_at": old_due_at,
                    }),
                    new_value=_audit_json({
                        "status": Status.IN_PROGRESS,
                        "due_at": new_due_at,
                    }),
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
    metadata_value = (
        event_data.model_dump().get("metadata")
        if hasattr(event_data, "model_dump")
        else getattr(event_data, "metadata_", None)
    )
    return Event(
        id=event_data.id,
        entity_type=event_data.entity_type,
        entity_id=event_data.entity_id,
        actor_type=event_data.actor_type,
        actor_user_id=event_data.actor_user_id,
        event_type=event_data.event_type,
        old_value=event_data.old_value,
        new_value=event_data.new_value,
        metadata_=metadata_value,
        idempotency_key=event_data.idempotency_key,
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
        return session.get(Comment, comment_id)


def count_comment_attachments(comment_id: str) -> int:
    with Session(engine) as session:
        return session.scalar(
            select(func.count(Attachment.id)).where(
                Attachment.comment_id == comment_id,
                Attachment.deleted_at.is_(None),
            )
        ) or 0


def create_attachment(attachment: Attachment, event_data: Event) -> Attachment:
    with Session(engine) as session:
        with session.begin():
            session.add(attachment)
            session.add(_event_from_data(event_data))
            comment = session.get(Comment, attachment.comment_id)
            if comment is not None:
                # Keep the counter update inside the same transaction as the
                # attachment insert.  Opening a second Session here can read
                # a snapshot that does not include the new attachment.
                comment.attachments_count = (comment.attachments_count or 0) + 1
        session.refresh(attachment)
        return attachment


def get_attachment(attachment_id: str) -> Attachment | None:
    with Session(engine) as session:
        return session.get(Attachment, attachment_id)


def get_comment_attachments(comment_id: str) -> list[Attachment]:
    with Session(engine) as session:
        return list(session.scalars(
            select(Attachment)
            .where(
                Attachment.comment_id == comment_id,
                Attachment.deleted_at.is_(None),
            )
            .order_by(Attachment.created_at.asc(), Attachment.id.asc())
        ).all())


def get_comments(
                ticket_id: str | None = None,
                limit: int | None = None,
                offset: int = 0,
                sort_by: str = DEFAULT_SORT_BY,
                sort_order: str = DEFAULT_SORT_ORDER) -> list[Comment]:
    with Session(engine) as session:
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


def get_ticket_history_events(
    ticket_id: str,
    limit: int,
    offset: int,
    comment_visibilities: tuple | None,
) -> list[Event]:
    """Return one chronological page of ticket and related comment events."""
    ticket_event = and_(
        Event.entity_type == EntityType.TICKET,
        Event.entity_id == ticket_id,
    )
    comment_event = and_(
        Event.entity_type == EntityType.COMMENT,
        Comment.ticket_id == ticket_id,
    )
    if comment_visibilities is not None:
        comment_event = and_(
            comment_event,
            Comment.visibility.in_(comment_visibilities),
        )

    statement = (
        select(Event)
        .outerjoin(
            Comment,
            and_(
                Event.entity_type == EntityType.COMMENT,
                Event.entity_id == Comment.id,
            ),
        )
        .where(or_(ticket_event, comment_event))
        .order_by(Event.created_at.asc(), Event.id.asc())
        .offset(offset)
        .limit(limit)
    )
    with Session(engine) as session:
        return list(session.scalars(statement).all())


# ================================================================
# ======================= ANALYSIS ===============================
ACTIVE_ANALYSIS_STATUSES = (
    AnalysisStatus.PENDING,
    AnalysisStatus.RUNNING,
)


def reserve_analysis_result(
    ticket_id: str,
    *,
    authorize_ticket: Callable[[Ticket], None],
    consume_allowance: Callable[[], object],
    build_result: Callable[[Ticket, list[Comment]], AnalysisResult],
) -> AnalysisReservation | None:
    """Serialize active-result detection, limiting, and durable creation."""
    with Session(engine, expire_on_commit=False) as session:
        try:
            if session.get_bind().dialect.name == "sqlite":
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            else:
                session.begin()

            ticket_statement = select(Ticket).where(Ticket.id == ticket_id)
            if session.get_bind().dialect.name != "sqlite":
                ticket_statement = ticket_statement.with_for_update()
            ticket = session.scalar(ticket_statement)
            if ticket is None:
                session.commit()
                return None

            authorize_ticket(ticket)
            active = session.scalar(
                select(AnalysisResult).where(
                    AnalysisResult.ticket_id == ticket_id,
                    AnalysisResult.status.in_(ACTIVE_ANALYSIS_STATUSES),
                )
            )
            if active is not None:
                session.commit()
                return AnalysisReservation(result=active, created=False)

            # This callback is intentionally after active duplicate detection.
            # Any exception rolls back the SQL reservation.
            consume_allowance()
            public_comments = list(session.scalars(
                select(Comment)
                .where(
                    Comment.ticket_id == ticket_id,
                    Comment.visibility == Visibility.PUBLIC,
                    Comment.deleted_at.is_(None),
                )
                .order_by(Comment.created_at.desc(), Comment.id.desc())
                .limit(10)
            ).all())
            result = build_result(ticket, public_comments)
            session.add(result)
            session.commit()
            return AnalysisReservation(result=result, created=True)
        except Exception:
            session.rollback()
            raise


def create_analysis_result(analysis: AnalysisResult) -> AnalysisResult:
    with Session(engine, expire_on_commit=False) as session:
        with session.begin():
            session.add(analysis)
        return analysis


def get_analysis_result(analysis_result_id: str) -> AnalysisResult | None:
    with Session(engine) as session:
        return session.get(AnalysisResult, analysis_result_id)


def get_analysis_result_by_job(job_id: str) -> AnalysisResult | None:
    with Session(engine) as session:
        statement = select(AnalysisResult).where(AnalysisResult.job_id == job_id)
        return session.scalar(statement)


def get_active_analysis_result(ticket_id: str) -> AnalysisResult | None:
    with Session(engine) as session:
        statement = select(AnalysisResult).where(
            AnalysisResult.ticket_id == ticket_id,
            AnalysisResult.status.in_(ACTIVE_ANALYSIS_STATUSES),
        )
        return session.scalar(statement)


def get_analysis_results_by_ticket(
    ticket_id: str,
    limit: int = DEFAULT_PAGE_LIMIT,
    offset: int = 0,
) -> list[AnalysisResult]:
    with Session(engine) as session:
        statement = (
            select(AnalysisResult)
            .where(AnalysisResult.ticket_id == ticket_id)
            .order_by(AnalysisResult.created_at.desc(), AnalysisResult.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(session.scalars(statement).all())


def attach_analysis_job(
    analysis_result_id: str,
    job_id: str,
    now: datetime,
) -> AnalysisResult | None:
    statement = (
        update(AnalysisResult)
        .where(
            AnalysisResult.id == analysis_result_id,
            AnalysisResult.job_id.is_(None),
        )
        .values(job_id=job_id, updated_at=now)
        .returning(AnalysisResult)
    )
    return _run_analysis_transition(statement)


def start_analysis_attempt(
    analysis_result_id: str,
    now: datetime,
) -> AnalysisResult | None:
    statement = (
        update(AnalysisResult)
        .where(
            AnalysisResult.id == analysis_result_id,
            AnalysisResult.status == AnalysisStatus.PENDING,
            AnalysisResult.attempt_count < 3,
        )
        .values(
            status=AnalysisStatus.RUNNING,
            attempt_count=AnalysisResult.attempt_count + 1,
            started_at=func.coalesce(AnalysisResult.started_at, now),
            updated_at=now,
        )
        .returning(AnalysisResult)
    )
    return _run_analysis_transition(statement)


def return_analysis_to_pending(
    analysis_result_id: str,
    now: datetime,
) -> AnalysisResult | None:
    statement = (
        update(AnalysisResult)
        .where(
            AnalysisResult.id == analysis_result_id,
            AnalysisResult.status == AnalysisStatus.RUNNING,
            AnalysisResult.attempt_count < 3,
        )
        .values(status=AnalysisStatus.PENDING, updated_at=now)
        .returning(AnalysisResult)
    )
    return _run_analysis_transition(statement)


def complete_analysis_result(
    analysis_result_id: str,
    summary: str,
    now: datetime,
    *,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> AnalysisResult | None:
    statement = (
        update(AnalysisResult)
        .where(
            AnalysisResult.id == analysis_result_id,
            AnalysisResult.status == AnalysisStatus.RUNNING,
        )
        .values(
            status=AnalysisStatus.COMPLETED,
            summary=summary,
            error_code=None,
            error_message=None,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            completed_at=now,
            updated_at=now,
        )
        .returning(AnalysisResult)
    )
    return _run_analysis_transition(statement)


def fail_analysis_result(
    analysis_result_id: str,
    *,
    expected_statuses: tuple[AnalysisStatus, ...],
    error_code: str,
    error_message: str,
    now: datetime,
) -> AnalysisResult | None:
    statement = (
        update(AnalysisResult)
        .where(
            AnalysisResult.id == analysis_result_id,
            AnalysisResult.status.in_(expected_statuses),
        )
        .values(
            status=AnalysisStatus.FAILED,
            summary=None,
            error_code=error_code,
            error_message=error_message,
            completed_at=now,
            updated_at=now,
        )
        .returning(AnalysisResult)
    )
    return _run_analysis_transition(statement)


def _run_analysis_transition(statement) -> AnalysisResult | None:
    with Session(engine, expire_on_commit=False) as session:
        with session.begin():
            return session.scalar(statement)
