import logging
from uuid import uuid4
from .enums import Role, Status, Tag, JobStatus
from src.models.jobs import JobResponse, JobStatusResponse, Job
import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import asc, desc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_id() -> str:
    return str(uuid4()) #do we really need this function?

COMMENT_BODY_MAX_LENGTH = 32000
DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 100
DEFAULT_SORT_BY="created_at"
DEFAULT_SORT_ORDER="desc"

SLA_HOURS = {
    Status.NEW: 2,
    Status.OPEN: 6,
    Status.IN_PROGRESS: 12,
    Status.REOPENED: 4
}

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def calculate_sla_due_at(status: Status, now: datetime) -> datetime | None:
    """Return the UTC deadline for one ticket status stage."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("SLA calculation requires a timezone-aware timestamp")

    hours = SLA_HOURS.get(status)
    if hours is None:
        return None
    return now.astimezone(timezone.utc) + timedelta(hours=hours)


ROLE_LEVELS = {
    Role.GUEST: 0,          # almost no access
    Role.USER: 1,           # normal client
    Role.AGENT_READONLY: 2, # support viewer/trainee
    Role.AGENT: 3,          # suppoer worker
    Role.MANAGER: 4,        # manages support team
    Role.ADMIN: 5,          # manages support/users/settings
    Role.SUPER_ADMIN: 6,    # highest human/admin role

    Role.BOT: 5,            # trusted automation role, similair to admin depending on endpoint
    Role.API: 5,            # trusted integration role, similair to admin depending on endpoint
}

TICKET_STATUS_TRANSITIONS = {
    Status.NEW: frozenset({Status.OPEN}),
    Status.OPEN: frozenset({Status.IN_PROGRESS}),
    Status.IN_PROGRESS: frozenset({Status.PENDING, Status.ON_HOLD, Status.RESOLVED}),
    Status.PENDING: frozenset({Status.IN_PROGRESS, Status.RESOLVED}),
    Status.ON_HOLD: frozenset({Status.IN_PROGRESS}),
    Status.RESOLVED: frozenset({Status.CLOSED, Status.IN_PROGRESS}),
    Status.CLOSED: frozenset({Status.REOPENED}),
    Status.REOPENED: frozenset({Status.IN_PROGRESS}),
}

# Assignment is an action-specific exception to the normal status graph. A
# transfer sends active work back to OPEN for the receiving agent, but terminal
# tickets must be reopened before they can be assigned again.
TICKET_ASSIGNABLE_STATUSES = frozenset({
    Status.NEW,
    Status.OPEN,
    Status.IN_PROGRESS,
    Status.PENDING,
    Status.ON_HOLD,
    Status.REOPENED,
})

STAFF_TRANSITION_ROLES = frozenset({
    Role.AGENT,
    Role.MANAGER,
    Role.ADMIN,
    Role.SUPER_ADMIN,
})

TICKET_TRANSITION_ROLES = {
    (old_status, new_status): STAFF_TRANSITION_ROLES
    for old_status, next_statuses in TICKET_STATUS_TRANSITIONS.items()
    for new_status in next_statuses
}
# Customers may accept a resolution or reopen their own closed ticket. The
# service still checks ticket ownership; this mapping only answers the role
# part of the rule.
TICKET_TRANSITION_ROLES[(Status.RESOLVED, Status.CLOSED)] = (
    STAFF_TRANSITION_ROLES | {Role.USER}
)
TICKET_TRANSITION_ROLES[(Status.CLOSED, Status.REOPENED)] = (
    STAFF_TRANSITION_ROLES | {Role.USER}
)


def is_valid_status_transition(old_status: Status, new_status: Status) -> bool:
    return new_status in TICKET_STATUS_TRANSITIONS.get(old_status, frozenset())


def can_role_transition_ticket(
    role: Role,
    old_status: Status,
    new_status: Status,
) -> bool:
    return role in TICKET_TRANSITION_ROLES.get((old_status, new_status), frozenset())


def serialize_tags(tags: list[Tag]) -> str:
    return json.dumps([tag.value for tag in tags])

def deserialize_tags(raw: str) -> list[Tag]:
    return [Tag(value) for value in json.loads(raw or "[]")]

def validate_required_text(value: str, field_name: str, max_length: int) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{field_name}_empty")
    if len(value) > max_length:
        raise ValueError(f"{field_name}_too_long")
    return value

    
def _audit_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    return value

def _audit_json(data: dict) -> str:
    return json.dumps({key: _audit_value(value) for key, value in data.items()})

def apply_sort_order(column, sort_order: str):
    match sort_order:
        case 'desc': return column.desc()
        case 'asc': return column.asc()

def translate_rq_status(rq_status: str) -> JobStatus:
    status_mapping = {
        "queued": JobStatus.QUEUED,
        "started": JobStatus.RUNNING,
        "finished": JobStatus.COMPLETED,
        "failed": JobStatus.FAILED,
        "deferred": JobStatus.DEFERRED,
        "scheduled": JobStatus.SCHEDULED,
        "stopped": JobStatus.STOPPED,
        "canceled": JobStatus.CANCELED,
        "rate_limited": JobStatus.RATE_LIMITED,
        "ready_to_enqueue": JobStatus.READY_TO_ENQUEUE,
    }
    return status_mapping.get(rq_status, JobStatus.UNKNOWN)


def raw_job_to_job_response(raw_job) -> Job:
    job = Job(
        id=raw_job.id,
        func_name=raw_job.func_name,
        status=raw_job.get_status(),
        result=raw_job.result,
        created_at=raw_job.created_at,
        enqueued_at=raw_job.enqueued_at,
        ended_at=raw_job.ended_at
    )
    return job
