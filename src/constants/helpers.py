import logging
from uuid import uuid4
from .enums import *
import json
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_id() -> str:
    return str(uuid4()) #do we really need this function?

COMMENT_BODY_MAX_LENGTH = 32000

SLA_HOURS = {
    Status.NEW: 2,
    Status.OPEN: 6,
    Status.IN_PROGRESS: 12,
    Status.REOPENED: 4
}

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

def is_valid_status_transition(old_status: Status, new_status: Status) -> bool:
    match(old_status):
        case Status.NEW:
            if new_status == Status.OPEN: return True
        case Status.OPEN:
            if new_status == Status.IN_PROGRESS: return True
        case Status.IN_PROGRESS:
            if new_status in [Status.PENDING, Status.ON_HOLD, Status.RESOLVED]: return True
            return False
        case Status.PENDING:
            if new_status in [Status.IN_PROGRESS, Status.RESOLVED]: return True
        case Status.ON_HOLD:
            if new_status == Status.IN_PROGRESS: return True
        case Status.RESOLVED:
            if new_status in [Status.CLOSED, Status.IN_PROGRESS]: return True
        case Status.CLOSED:
            if new_status == Status.REOPENED: return True
        case Status.REOPENED:
            if new_status == Status.IN_PROGRESS: return True
    return False


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
