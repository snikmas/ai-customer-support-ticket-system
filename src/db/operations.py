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
from sqlalchemy import and_, case, func, or_, select, update
from datetime import datetime, timedelta, timezone
from src.constants import (
    ActorType,
    ANALYSIS_EXECUTION_LEASE_SECONDS,
    AnalysisStatus,
    AvailabilityStatus,
    EntityType,
    EventType,
    Role,
    StartWorkOutcome,
    Status,
    TICKET_ASSIGNABLE_STATUSES,
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
from src.exceptions.domain import (
    AgentAtCapacityError,
    AgentHasActiveTicketsError,
    AgentProfileNotFoundError,
    AgentUnavailableError,
    AttachmentValidationError,
    FinalAdminAccessError,
    InactiveRoutingCatalogError,
    InvalidAssigneeError,
    LastSuperAdminError,
    TicketDeletedError,
    TicketStatusConflictError,
)


ACTIVE_TICKET_STATUSES = (
    Status.OPEN,
    Status.IN_PROGRESS,
    Status.PENDING,
    Status.ON_HOLD,
    Status.REOPENED,
)


# Ticket-mutation lock order (must stay consistent across claim / routing /
# start-work / update / assign):
#
#     Ticket  ->  Department  ->  AgentProfile
#
# The ticket row is always the first row locked, so two writers that touch the
# same ticket serialize before either reads shared state. A department lock then
# serializes automatic/manual assignment decisions for one queue, and the
# AgentProfile lock is taken last so workload/eligibility reads cannot interleave
# with a competing assignment. Never take these locks in the reverse order:
# doing so can deadlock two writers that touch the same ticket and department.
#
# PostgreSQL relies on SELECT ... FOR UPDATE. SQLite ignores row locks, so the
# write transaction first runs "BEGIN IMMEDIATE" to acquire the database write
# lock before any read; this gives SQLite the same single-writer boundary.


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


@dataclass(frozen=True)
class TicketAccessState:
    creator_user_id: str
    assigned_agent_id: str | None
    status: Status
    deleted_at: datetime | None


def get_ticket_access_state(ticket_id: str) -> TicketAccessState | None:
    """Read authorization fields from SQL even when ticket content is cached."""
    with Session(engine) as session:
        row = session.execute(select(
            Ticket.creator_user_id, Ticket.assigned_agent_id,
            Ticket.status, Ticket.deleted_at,
        ).where(Ticket.id == ticket_id)).first()
        return TicketAccessState(*row) if row is not None else None


@dataclass(frozen=True)
class TicketMutationGuard:
    """Snapshot of the state a service decision depended on.

    A caller that read a ticket and authorized a mutation passes the fields it
    based that decision on. The mutation transaction re-reads the locked row and
    rejects the write with a conflict when any guarded field has changed, so a
    stale writer cannot overwrite a concurrent reassignment, status change, or
    deletion.
    """

    assigned_agent_id: str | None
    status: Status
    department_id: str | None
    deleted_at: datetime | None


@dataclass(frozen=True)
class UserLifecycleGuards:
    """Count-based protections enforced in the same transaction as the write.

    ``protect_last_super_admin`` is set by every path that can remove an active
    Super Admin. ``protect_final_admin_access`` is set only when the acting user
    changes their own administrative access, matching the rule that an
    administrator may not strand an installation without any administrator.

    The decision spans several user rows, so a per-target row lock cannot make
    it safe. Both flags are re-checked after the shared lifecycle lock below is
    held, never from a value read before the transaction began.
    """

    protect_last_super_admin: bool = False
    protect_final_admin_access: bool = False


def _require_sqlite_write_lock(session: Session) -> None:
    """Acquire SQLite's write lock before reading (no effective row locks)."""
    if session.get_bind().dialect.name == "sqlite":
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")


# One fixed lock key serializes every user-lifecycle mutation whose decision
# spans several user rows (the last active Super Admin, final administrative
# access) and the role/profile transition itself. SQLite already has a single
# writer boundary in BEGIN IMMEDIATE; PostgreSQL gets the same boundary from a
# transaction-level advisory lock that is released automatically on
# commit/rollback. Never gate this on a value read before the lock is held.
_USER_LIFECYCLE_LOCK_KEY = 0x75736572  # arbitrary fixed key


def _acquire_user_lifecycle_lock(session: Session) -> None:
    if session.get_bind().dialect.name == "sqlite":
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
    else:
        session.connection().exec_driver_sql(
            f"SELECT pg_advisory_xact_lock({_USER_LIFECYCLE_LOCK_KEY})"
        )


def _lock_ticket_row(session: Session, ticket_id: str) -> Ticket | None:
    return session.scalar(
        select(Ticket).where(Ticket.id == ticket_id).with_for_update()
    )


def _require_expected_ticket_state(
    ticket: Ticket,
    expected: TicketMutationGuard,
) -> None:
    if (
        ticket.assigned_agent_id != expected.assigned_agent_id
        or ticket.status != expected.status
        or ticket.department_id != expected.department_id
        or ticket.deleted_at != expected.deleted_at
    ):
        raise TicketStatusConflictError(
            "Ticket changed since it was read",
            code="ticket_state_conflict",
        )


def _lock_department(session: Session, department_id: str | None) -> None:
    if department_id is None:
        return
    session.execute(
        select(Department.id)
        .where(Department.id == department_id)
        .with_for_update()
    )


def _lock_and_validate_department(
    session: Session,
    department_id: str | None,
) -> None:
    _lock_department(session, department_id)
    if department_id is None:
        return
    department = session.get(Department, department_id)
    if department is None or department.deleted_at is not None:
        raise InactiveRoutingCatalogError(
            "Ticket department is missing or archived"
        )


def _lock_and_validate_assignee(
    session: Session,
    department_id: str | None,
    agent_id: str | None,
) -> None:
    """Lock and validate a receiving agent against the destination department.

    Follows the documented lock order: the ticket row is already locked, the
    department is locked next, and the agent profile last. A department is only
    compared when the ticket has one, which keeps direct database callers that
    seed a ticket without routing metadata working.
    """
    _lock_department(session, department_id)
    profile = session.scalar(
        select(AgentProfile)
        .where(AgentProfile.user_id == agent_id)
        .with_for_update()
    )
    agent = session.get(User, agent_id)
    if (
        agent is None
        or agent.role != Role.AGENT
        or agent.user_status != UserStatus.ACTIVE
        or agent.deleted_at is not None
        or profile is None
        or profile.availability_status != AvailabilityStatus.AVAILABLE
    ):
        raise InvalidAssigneeError()
    if department_id is not None:
        department = session.get(Department, department_id)
        if (
            department is None
            or department.deleted_at is not None
            or profile.department_id != department_id
        ):
            raise InvalidAssigneeError(code="assignee_department_mismatch")


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
            previous_refresh_token_hash=old_refresh_session.previous_refresh_token_hash,
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
        return session.query(RefreshSession).filter(
            or_(
                RefreshSession.refresh_token_hash == hash_token,
                RefreshSession.previous_refresh_token_hash == hash_token,
            )
        ).first()
    
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

def rotate_refresh_session(session_id, current_hash, previous_hash, created_at, expires_at, hash_ref_token, revoked_at, event_data: Event | None = None) -> RefreshSession | None:
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
                    previous_refresh_token_hash=previous_hash,
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


def _count_active_superadmins(session: Session) -> int:
    return session.scalar(
        select(func.count(User.id)).where(
            User.role == Role.SUPER_ADMIN,
            User.user_status == UserStatus.ACTIVE,
            User.deleted_at.is_(None),
        )
    ) or 0


def _count_active_administrators(session: Session) -> int:
    return session.scalar(
        select(func.count(User.id)).where(
            User.role.in_((Role.ADMIN, Role.SUPER_ADMIN)),
            User.user_status == UserStatus.ACTIVE,
            User.deleted_at.is_(None),
        )
    ) or 0


def count_active_superadmins() -> int:
    with Session(engine) as session:
        return _count_active_superadmins(session)


def count_active_administrators() -> int:
    with Session(engine) as session:
        return _count_active_administrators(session)


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


def get_assignment_candidates(
    department_id: str | None = None,
    *,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[tuple[User, AgentProfile, int]]:
    """Agents a manager may manually assign, with their current workload.

    Manual assignment requires a live (AVAILABLE) agent in a live department.
    Capacity is deliberately NOT a filter here: the accepted policy lets a
    manager override capacity with an explicit assignment, so at-capacity
    agents remain selectable. Automatic routing still enforces capacity.
    The department filter is optional so administrators can still page through
    candidates when triaging before routing.
    """

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
        select(User, AgentProfile, active_ticket_count)
        .join(AgentProfile, AgentProfile.user_id == User.id)
        .join(Department, Department.id == AgentProfile.department_id)
        .where(
            User.role == Role.AGENT,
            User.user_status == UserStatus.ACTIVE,
            User.deleted_at.is_(None),
            AgentProfile.availability_status == AvailabilityStatus.AVAILABLE,
            Department.deleted_at.is_(None),
        )
    )
    if department_id is not None:
        statement = statement.where(AgentProfile.department_id == department_id)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            or_(
                User.nickname.ilike(pattern),
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
                User.email.ilike(pattern),
            )
        )
    statement = (
        statement.order_by(
            active_ticket_count.asc(),
            AgentProfile.last_assigned_at.asc().nulls_first(),
            User.id.asc(),
        )
        .offset(offset)
        .limit(limit)
    )
    with Session(engine) as session:
        return [
            (user, profile, workload)
            for user, profile, workload in session.execute(statement).all()
        ]


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


def _lock_agent_profile(session: Session, user_id: str) -> AgentProfile | None:
    """Lock the AgentProfile row following the Department -> AgentProfile order.

    The department is locked first so this never inverts the ticket-mutation
    lock order. SQLite ignores row locks but the surrounding transaction has
    already taken BEGIN IMMEDIATE, which gives the same single-writer boundary.
    """
    profile = session.get(AgentProfile, user_id)
    if profile is not None:
        _lock_department(session, profile.department_id)
    return session.scalar(
        select(AgentProfile)
        .where(AgentProfile.user_id == user_id)
        .with_for_update()
    )


def _ensure_non_routing_agent_profile(
    session: Session,
    user_id: str,
    now: datetime,
) -> None:
    """Create or repair exactly one AgentProfile that cannot receive work yet.

    A freshly promoted agent is OFFLINE with no department and zero capacity
    until a manager configures it, so routing can never select an unconfigured
    profile.
    """
    profile = session.get(AgentProfile, user_id)
    if profile is None:
        session.add(
            AgentProfile(
                user_id=user_id,
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
        )
        return
    profile.availability_status = AvailabilityStatus.OFFLINE
    profile.availability_reason = "profile_setup_required"
    profile.availability_note = None
    profile.unavailable_until = None
    profile.max_active_tickets = 0
    profile.department_id = None
    profile.updated_at = now


def _apply_agent_role_lifecycle(
    session: Session,
    user: User,
    new_role: Role,
    new_status: UserStatus,
    new_deleted: datetime | None,
    now: datetime,
) -> None:
    """Keep the AgentProfile consistent with every role/status change.

    Leaving the Agent role (or becoming inactive/deleted) is rejected while the
    user still owns active tickets, and the profile is taken offline. Entering
    the Agent role creates or repairs a safe non-routing profile. The profile
    row is locked before the workload count so a concurrent router cannot slip
    an assignment between the check and the role write.
    """
    old_role = user.role

    leaves_agent = old_role is Role.AGENT and (
        new_role is not Role.AGENT
        or new_status is not UserStatus.ACTIVE
        or new_deleted is not None
    )
    if leaves_agent:
        profile = _lock_agent_profile(session, user.id)
        active_ticket_count = _count_active_assigned_tickets(session, user.id)
        if active_ticket_count:
            raise AgentHasActiveTicketsError(active_ticket_count)
        reason = (
            "role_changed_to_manager"
            if new_role is Role.MANAGER
            else "role_changed"
        )
        if profile is None:
            # Supports agents created before AgentProfile existed.
            profile = AgentProfile(
                user_id=user.id,
                availability_status=AvailabilityStatus.OFFLINE,
                availability_reason=reason,
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
            profile.availability_reason = reason
            profile.unavailable_until = None
            profile.updated_at = now
        return

    if old_role is not Role.AGENT and new_role is Role.AGENT:
        _ensure_non_routing_agent_profile(session, user.id, now)


def _enforce_user_lifecycle_guards(
    session: Session,
    user: User,
    *,
    new_role: Role,
    new_status: UserStatus,
    new_deleted: datetime | None,
    guards: UserLifecycleGuards | None,
) -> None:
    """Re-check the count-based protections under the shared lifecycle lock."""
    if guards is None:
        return

    removes_super_admin = user.role is Role.SUPER_ADMIN and (
        new_role is not Role.SUPER_ADMIN
        or new_status is not UserStatus.ACTIVE
        or new_deleted is not None
    )
    if (
        removes_super_admin
        and guards.protect_last_super_admin
        and _count_active_superadmins(session) <= 1
    ):
        raise LastSuperAdminError()

    removes_admin_access = user.role in {Role.ADMIN, Role.SUPER_ADMIN} and (
        new_role not in {Role.ADMIN, Role.SUPER_ADMIN}
        or new_status is not UserStatus.ACTIVE
        or new_deleted is not None
    )
    if (
        removes_admin_access
        and guards.protect_final_admin_access
        and _count_active_administrators(session) <= 1
    ):
        raise FinalAdminAccessError()


def _revoke_all_user_refresh_sessions(
    session: Session,
    user_id: str,
    revoked_at: datetime,
) -> None:
    """Revoke every live refresh session for a user in the caller's transaction.

    The conditional UPDATE races safely with refresh rotation: whichever writer
    reaches the row first wins, and a rotation that commits first is still
    revoked because it leaves ``revoked_at`` NULL until then.
    """
    session.execute(
        update(RefreshSession)
        .where(
            RefreshSession.user_id == user_id,
            RefreshSession.revoked_at.is_(None),
        )
        .values(revoked_at=revoked_at)
    )


def update_user(
    id: str,
    new_info: dict,
    event_data: Event | None = None,
    guards: UserLifecycleGuards | None = None,
    revoke_refresh_sessions: bool = False,
) -> User | None:
    with Session(engine) as session:
        with session.begin():
            _acquire_user_lifecycle_lock(session)

            user = session.get(User, id)
            if user is None:
                return None

            now = datetime.now(timezone.utc)
            new_role = new_info.get("role", user.role)
            new_status = new_info.get("user_status", user.user_status)
            new_deleted = new_info.get("deleted_at", user.deleted_at)

            _enforce_user_lifecycle_guards(
                session,
                user,
                new_role=new_role,
                new_status=new_status,
                new_deleted=new_deleted,
                guards=guards,
            )
            _apply_agent_role_lifecycle(
                session,
                user,
                new_role,
                new_status,
                new_deleted,
                now,
            )

            if revoke_refresh_sessions and "password" in new_info:
                _revoke_all_user_refresh_sessions(session, user.id, now)

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


def delete_user(
    id: str,
    delete_info: dict,
    event_data: Event | None = None,
    guards: UserLifecycleGuards | None = None,
) -> bool:
    with Session(engine) as session:
        with session.begin():
            _acquire_user_lifecycle_lock(session)

            user = session.get(User, id)
            if user is None:
                return False

            now = datetime.now(timezone.utc)
            new_status = delete_info.get("user_status", user.user_status)
            new_deleted = delete_info.get("deleted_at", user.deleted_at)

            _enforce_user_lifecycle_guards(
                session,
                user,
                new_role=user.role,
                new_status=new_status,
                new_deleted=new_deleted,
                guards=guards,
            )
            _apply_agent_role_lifecycle(
                session,
                user,
                user.role,
                new_status,
                new_deleted,
                now,
            )

            for field, value in delete_info.items():
                setattr(user, field, value)
            if event_data is not None:
                session.add(_event_from_data(event_data))

        return True
        
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
            'priority': case(
                *((Ticket.priority == priority, priority.value) for priority in Priority),
                else_=0,
            ),
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
    """Return one bounded, deterministic, fair reconciliation page.

    Fairness: waiting tickets are ordered by ``routing_attempted_at`` with NULLs
    (never attempted) first, then by ``created_at`` and ``id``. The dispatcher
    stamps each ticket it enqueues, so a ticket that cannot be assigned now
    rotates behind both never-attempted tickets and tickets attempted longer
    ago. With ``W`` waiting tickets and batch size ``B``, a stable waiting set
    is fully visited once per ``ceil(W / B)`` reconciliation passes, which is the
    finite recovery bound. The order is persisted on the ticket, so it survives
    a process restart and is never an in-memory cursor.

    New tickets enter with a NULL attempt time (first), then are stamped on
    their first pass, so a bounded arrival rate cannot reset progress. If
    arrivals exceed ``B`` per pass the waiting set grows and no bounded scanner
    can guarantee a finite wait; that is a capacity limit, not a correctness
    bug. Deleted or assigned tickets simply leave the predicate.

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
        .order_by(
            Ticket.routing_attempted_at.asc().nulls_first(),
            Ticket.created_at.asc(),
            Ticket.id.asc(),
        )
        .limit(limit)
    )
    with Session(engine) as session:
        return list(session.scalars(statement).all())


def record_routing_attempts(ticket_ids: list[str], now: datetime) -> int:
    """Stamp one bounded page of tickets as routed-through the reconciler.

    The write is a single UPDATE restricted to the given ids and to tickets that
    are still waiting, so it never resurrects assigned/deleted work and never
    scans the whole table. Callers invoke it after the read session is closed,
    so no database session spans the Redis enqueue. Recording an attempt only
    changes rotation order, never ticket state, so a lost or delayed write can
    delay a retry by at most one rotation, never drop it.
    """
    if not ticket_ids:
        return 0
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Routing attempt time must be timezone-aware")

    with Session(engine) as session, session.begin():
        result = session.execute(
            update(Ticket)
            .where(
                Ticket.id.in_(ticket_ids),
                Ticket.deleted_at.is_(None),
                Ticket.status == Status.NEW,
                Ticket.assigned_agent_id.is_(None),
            )
            .values(routing_attempted_at=now)
        )
    return result.rowcount


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


def update_ticket(
    id: str,
    new_info: dict,
    event_data: Event | None = None,
    expected: TicketMutationGuard | None = None,
) -> Ticket | None:
    with Session(engine) as session:
        with session.begin():
            _require_sqlite_write_lock(session)
            ticket = _lock_ticket_row(session, id)

            if ticket is None:
                return None

            # Re-run the correctness-critical checks inside the same
            # transaction that performs the mutation. A caller passes the
            # state it authorized against; if it changed, the stale write loses.
            if expected is not None:
                _require_expected_ticket_state(ticket, expected)

            old_assignee_id = ticket.assigned_agent_id
            now = event_data.created_at if event_data is not None else utc_now()

            if "assigned_agent_id" in new_info and new_info["assigned_agent_id"] is not None:
                if ticket.status not in TICKET_ASSIGNABLE_STATUSES:
                    raise TicketStatusConflictError(
                        "Terminal tickets must be reopened before assignment",
                    )
                # Validate the proposed assignee against the *proposed*
                # destination department, not the ticket's old department.
                _lock_and_validate_assignee(
                    session,
                    new_info.get("department_id", ticket.department_id),
                    new_info["assigned_agent_id"],
                )
            elif "department_id" in new_info:
                _lock_and_validate_department(session, new_info["department_id"])

            skill_ids = new_info.pop("skill_ids", None)
            # The service layer computes due_at itself; only derive it here for
            # callers that change status/priority without providing one.
            if (
                ("status" in new_info or "priority" in new_info)
                and "due_at" not in new_info
            ):
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
            if session.get_bind().dialect.name == "sqlite":
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            ticket = session.scalar(select(Ticket).where(Ticket.id == ticket_id).with_for_update())
            if ticket is None or ticket.deleted_at is not None or ticket.status != Status.NEW or ticket.assigned_agent_id is not None:
                return None
            if ticket.department_id:
                session.execute(select(Department.id).where(Department.id == ticket.department_id).with_for_update())
            profile = session.scalar(select(AgentProfile).where(AgentProfile.user_id == assigned_id).with_for_update())
            agent = session.get(User, assigned_id)
            if agent is None or agent.role != Role.AGENT or agent.user_status != UserStatus.ACTIVE or agent.deleted_at is not None or profile is None:
                raise InvalidAssigneeError()
            department = session.get(Department, ticket.department_id) if ticket.department_id else None
            if department is None or department.deleted_at is not None or profile.department_id != ticket.department_id:
                raise InvalidAssigneeError(code="assignee_department_mismatch")
            if profile.availability_status != AvailabilityStatus.AVAILABLE:
                raise AgentUnavailableError()
            workload = session.scalar(select(func.count()).select_from(Ticket).where(Ticket.assigned_agent_id == assigned_id, Ticket.deleted_at.is_(None), Ticket.status.in_(ACTIVE_TICKET_STATUSES)))
            if workload >= profile.max_active_tickets:
                raise AgentAtCapacityError()

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

            if session.get_bind().dialect.name != "sqlite" and ticket.department_id:
                # Lock before the workload query starts. Locking a candidate
                # inside that query can retain a count from before it waited.
                # One department serializes competing automatic assignments.
                session.execute(
                    select(Department.id)
                    .where(Department.id == ticket.department_id)
                    .with_for_update()
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


def assign_ticket(
    ticket_id: str,
    assigned_agent_id: str,
    event_data: Event | None = None,
    expected: TicketMutationGuard | None = None,
) -> Ticket | None:
    with Session(engine) as session:
        with session.begin():
            _require_sqlite_write_lock(session)
            ticket = _lock_ticket_row(session, ticket_id)
            if ticket is None:
                return None

            if expected is not None:
                _require_expected_ticket_state(ticket, expected)
            if ticket.deleted_at is not None:
                raise TicketDeletedError()
            if ticket.status not in TICKET_ASSIGNABLE_STATUSES:
                raise TicketStatusConflictError(
                    "Terminal tickets must be reopened before assignment",
                )

            # Ticket row already locked; validate the receiving agent against
            # the ticket department while holding Department then AgentProfile.
            _lock_and_validate_assignee(session, ticket.department_id, assigned_agent_id)

            user = session.get(User, assigned_agent_id)
            if user is None:
                return None

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


def create_attachment_guarded(
    attachment: Attachment,
    event_data: Event,
    *,
    max_attachments: int,
    authorize: Callable[[Comment | None, Ticket | None, User | None], None],
) -> Attachment:
    """Commit one attachment while holding the per-comment write boundary.

    All upload paths serialize on the comment row: PostgreSQL takes
    ``SELECT ... FOR UPDATE`` and SQLite takes its single-writer
    ``BEGIN IMMEDIATE`` lock before the counter is read. The cap check, the
    ``authorize`` re-check (deletion, visibility, author, current ticket access,
    account state, write permission) and the counter increment therefore run in
    the same transaction as the insert.

    ``authorize`` receives the freshly locked comment and ticket rows plus the
    actor's current user row, and must raise a domain exception to reject.
    Because the blob is written before this transaction, the caller is
    responsible for removing an uncommitted blob when this function raises.
    """
    with Session(engine, expire_on_commit=False) as session:
        with session.begin():
            _require_sqlite_write_lock(session)
            comment = session.scalar(
                select(Comment)
                .where(Comment.id == attachment.comment_id)
                .with_for_update()
            )
            ticket = None
            if comment is not None:
                ticket = session.scalar(
                    select(Ticket)
                    .where(Ticket.id == comment.ticket_id)
                    .with_for_update()
                )

            actor = (
                session.get(User, attachment.created_by_user_id)
                if attachment.created_by_user_id
                else None
            )
            authorize(comment, ticket, actor)

            current_count = session.scalar(
                select(func.count(Attachment.id)).where(
                    Attachment.comment_id == attachment.comment_id,
                    Attachment.deleted_at.is_(None),
                )
            ) or 0
            if current_count >= max_attachments:
                raise AttachmentValidationError(
                    f"A comment can have at most {max_attachments} files",
                    code="attachment_count_exceeded",
                )

            session.add(attachment)
            session.add(_event_from_data(event_data))
            if comment is not None:
                # Atomic increment: a read-modify-write here would lose updates
                # when two uploads for the same comment interleave.
                session.execute(
                    update(Comment)
                    .where(Comment.id == comment.id)
                    .values(attachments_count=Comment.attachments_count + 1)
                )

        return attachment


def get_attachment(attachment_id: str) -> Attachment | None:
    with Session(engine) as session:
        return session.get(Attachment, attachment_id)


def get_all_attachment_storage_keys() -> set[str]:
    """Every storage key referenced by a committed attachment row.

    Deleted rows are included on purpose: a cleanup command must never remove
    bytes that any attachment metadata row still points at.
    """
    with Session(engine) as session:
        return set(session.scalars(select(Attachment.storage_key)).all())


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
                sort_order: str = DEFAULT_SORT_ORDER,
                *,
                visibilities: tuple | None = None,
                include_deleted: bool = False) -> list[Comment]:
    with Session(engine) as session:
        sort_columns = {
            "created_at": Comment.created_at,
            "updated_at": Comment.updated_at,
        }
        sort_col = sort_columns[sort_by]

        order_exp = apply_sort_order(sort_col, sort_order)

        # Visibility and soft-delete filtering belong in SQL so LIMIT/OFFSET
        # pages are not shortened by rows the requester cannot see.
        query = select(Comment).order_by(order_exp).offset(offset)
        if limit:
            query = query.limit(limit)

        if not include_deleted:
            query = query.where(Comment.deleted_at.is_(None))
        if visibilities is not None:
            query = query.where(Comment.visibility.in_(visibilities))

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

def update_comment_with_event(
    comment_id: str,
    mutate: Callable[[Comment, Ticket | None, User | None], tuple[dict, Event]],
    *,
    actor_user_id: str | None = None,
) -> Comment | None:
    """Apply one comment update and its audit event in a single transaction.

    ``mutate`` runs inside the write transaction with the freshly locked comment
    and ticket rows plus the actor's current persisted user row. It must re-check
    current authorization against those rows and raise a domain exception to
    reject, then return the fields to apply and an audit event built from the
    locked state. Because the re-check, the write, and the event share one
    transaction and one row lock, a request that read a public comment before it
    was restricted can no longer republish it.

    ``actor_user_id`` loads the requester's row ``FOR UPDATE`` so a role change
    or ban committed before this boundary is seen instead of trusting the role
    claim captured when the request first arrived. The user row is locked first,
    matching the user-lifecycle lock order, so a comment write cannot deadlock
    against a role or profile transition.
    """
    with Session(engine, expire_on_commit=False) as session:
        with session.begin():
            _require_sqlite_write_lock(session)
            actor = (
                session.scalar(
                    select(User).where(User.id == actor_user_id).with_for_update()
                )
                if actor_user_id is not None
                else None
            )
            comment = session.scalar(
                select(Comment).where(Comment.id == comment_id).with_for_update()
            )
            if comment is None:
                return None
            ticket = session.scalar(
                select(Ticket).where(Ticket.id == comment.ticket_id).with_for_update()
            )

            new_info, event_data = mutate(comment, ticket, actor)

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
            if event is None:
                return False
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


def mark_analysis_dispatched(
    analysis_result_id: str,
    job_id: str,
    now: datetime,
    *,
    expected_status: AnalysisStatus = AnalysisStatus.PENDING,
) -> AnalysisResult | None:
    """Record one dispatch attempt on a not-yet-running row.

    Guarded by ``expected_status`` so a reconciler that raced a worker which
    already started the provider call cannot re-label the row. The dispatch
    identity is stable, so two reconcilers writing the same ``job_id`` is
    harmless.
    """
    statement = (
        update(AnalysisResult)
        .where(
            AnalysisResult.id == analysis_result_id,
            AnalysisResult.status == expected_status,
        )
        .values(
            job_id=job_id,
            dispatch_count=AnalysisResult.dispatch_count + 1,
            updated_at=now,
        )
        .returning(AnalysisResult)
    )
    return _run_analysis_transition(statement)


def get_reconcilable_analysis_results(
    limit: int,
    now: datetime,
) -> list[AnalysisResult]:
    """Return work the bounded reconciler must look at, oldest first.

    This deliberately selects only two shapes:

    * PENDING rows, whose provider call has either not happened or is known to
      have failed, and
    * RUNNING rows whose lease is missing or expired, i.e. abandoned work.

    A RUNNING row with a live lease is not returned. Terminal rows are never
    returned, so the reconciler cannot rerun completed work just because an RQ
    result expired.

    Fairness: rows are ordered by ``reconciliation_attempted_at`` with NULLs
    (never considered) first, then by ``created_at`` and ``id``. The reconciler
    stamps every row it considers, so a PENDING row whose RQ job is still live
    rotates behind never-considered and older-considered rows instead of
    permanently occupying the first page. With ``W`` recoverable rows and batch
    size ``B``, a stable set is fully visited once per ``ceil(W / B)`` passes:
    that is the finite recovery bound. The order is persisted on the row, so it
    survives a restart and is never an in-memory cursor.
    """
    statement = (
        select(AnalysisResult)
        .where(
            or_(
                AnalysisResult.status == AnalysisStatus.PENDING,
                and_(
                    AnalysisResult.status == AnalysisStatus.RUNNING,
                    or_(
                        AnalysisResult.lease_expires_at.is_(None),
                        AnalysisResult.lease_expires_at <= now,
                    ),
                ),
            )
        )
        .order_by(
            AnalysisResult.reconciliation_attempted_at.asc().nulls_first(),
            AnalysisResult.created_at.asc(),
            AnalysisResult.id.asc(),
        )
        .limit(limit)
    )
    with Session(engine) as session:
        return list(session.scalars(statement).all())


def record_analysis_reconciliation_attempts(
    analysis_result_ids: list[str],
    now: datetime,
) -> int:
    """Stamp one bounded page of analysis rows as considered by the reconciler.

    A single UPDATE restricted to the given ids, so it never scans the table and
    never changes analysis state -- only rotation order. Callers invoke it after
    the read session and enqueue work are done, so no database session spans
    Redis. Recording an attempt only changes the order in which a later pass
    sees the row, never whether the row is dispatched, so a lost or delayed
    write can defer a retry by at most one rotation and never drop it.
    """
    if not analysis_result_ids:
        return 0
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Reconciliation attempt time must be timezone-aware")

    with Session(engine) as session, session.begin():
        result = session.execute(
            update(AnalysisResult)
            .where(AnalysisResult.id.in_(analysis_result_ids))
            .values(reconciliation_attempted_at=now)
        )
    return result.rowcount


def start_analysis_attempt(
    analysis_result_id: str,
    now: datetime,
    *,
    execution_id: str | None = None,
    lease_seconds: int | None = None,
) -> AnalysisResult | None:
    """Claim a PENDING row for one provider attempt under a bounded lease.

    ``attempt_count`` counts PROVIDER attempts and is capped at 3. The lease is
    a separate, longer wall-clock deadline that lets the reconciler distinguish
    a healthy slow call from an abandoned one.
    """
    lease_seconds = (
        ANALYSIS_EXECUTION_LEASE_SECONDS if lease_seconds is None else lease_seconds
    )
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
            execution_id=execution_id or generate_id(),
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            updated_at=now,
        )
        .returning(AnalysisResult)
    )
    return _run_analysis_transition(statement)


def return_analysis_to_pending(
    analysis_result_id: str,
    now: datetime,
    *,
    execution_id: str | None = None,
) -> AnalysisResult | None:
    """Release a RUNNING row back to PENDING after a known provider failure.

    When ``execution_id`` is supplied the write only succeeds for the worker
    that still owns the row. A stale worker cannot send new work back to PENDING.
    """
    conditions = [
        AnalysisResult.id == analysis_result_id,
        AnalysisResult.status == AnalysisStatus.RUNNING,
        AnalysisResult.attempt_count < 3,
    ]
    if execution_id is not None:
        conditions.append(AnalysisResult.execution_id == execution_id)
    statement = (
        update(AnalysisResult)
        .where(*conditions)
        .values(
            status=AnalysisStatus.PENDING,
            execution_id=None,
            lease_expires_at=None,
            updated_at=now,
        )
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
    execution_id: str | None = None,
) -> AnalysisResult | None:
    """Store a provider result only for the current, non-expired owner.

    When ``execution_id`` is supplied, both the owner token and a live lease
    must match. This rejects a late completion from an expired worker and a
    completion from an obsolete execution after recovery restarted the row.
    """
    conditions = [
        AnalysisResult.id == analysis_result_id,
        AnalysisResult.status == AnalysisStatus.RUNNING,
    ]
    if execution_id is not None:
        conditions.append(AnalysisResult.execution_id == execution_id)
        conditions.append(AnalysisResult.lease_expires_at.is_not(None))
        conditions.append(AnalysisResult.lease_expires_at > now)
    statement = (
        update(AnalysisResult)
        .where(*conditions)
        .values(
            status=AnalysisStatus.COMPLETED,
            summary=summary,
            error_code=None,
            error_message=None,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            completed_at=now,
            lease_expires_at=None,
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
    execution_id: str | None = None,
) -> AnalysisResult | None:
    """Move a row to FAILED under an optional owner/lease guard.

    The API-side enqueue failure passes no ``execution_id`` because no execution
    exists yet. A worker-owned permanent failure passes its token so a stale
    worker cannot fail a row that has since been recovered or restarted.
    """
    conditions = [
        AnalysisResult.id == analysis_result_id,
        AnalysisResult.status.in_(expected_statuses),
    ]
    if execution_id is not None:
        conditions.append(AnalysisResult.execution_id == execution_id)
        conditions.append(AnalysisResult.lease_expires_at.is_not(None))
        conditions.append(AnalysisResult.lease_expires_at > now)
    statement = (
        update(AnalysisResult)
        .where(*conditions)
        .values(
            status=AnalysisStatus.FAILED,
            summary=None,
            error_code=error_code,
            error_message=error_message,
            completed_at=now,
            lease_expires_at=None,
            updated_at=now,
        )
        .returning(AnalysisResult)
    )
    return _run_analysis_transition(statement)


def abandon_expired_analysis_result(
    analysis_result_id: str,
    *,
    execution_id: str | None,
    error_code: str,
    error_message: str,
    now: datetime,
) -> AnalysisResult | None:
    """Move an expired worker attempt to FAILED, but only the observed owner.

    The reconciler passes the ``execution_id`` it actually selected and the
    conditions require the row to still be RUNNING under that same owner with a
    still-expired lease. If a new live attempt took over between the read and
    this write, zero rows match and the newer attempt is untouched.
    """
    conditions = [
        AnalysisResult.id == analysis_result_id,
        AnalysisResult.status == AnalysisStatus.RUNNING,
        or_(
            AnalysisResult.lease_expires_at.is_(None),
            AnalysisResult.lease_expires_at <= now,
        ),
    ]
    if execution_id is None:
        conditions.append(AnalysisResult.execution_id.is_(None))
    else:
        conditions.append(AnalysisResult.execution_id == execution_id)
    statement = (
        update(AnalysisResult)
        .where(*conditions)
        .values(
            status=AnalysisStatus.FAILED,
            summary=None,
            error_code=error_code,
            error_message=error_message,
            completed_at=now,
            lease_expires_at=None,
            updated_at=now,
        )
        .returning(AnalysisResult)
    )
    return _run_analysis_transition(statement)


def _run_analysis_transition(statement) -> AnalysisResult | None:
    with Session(engine, expire_on_commit=False) as session:
        with session.begin():
            return session.scalar(statement)
