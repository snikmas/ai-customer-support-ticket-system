import logging
from uuid import uuid4
from .enums import *

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_id():
    return str(uuid4()) #do we really need this function?

SLA_HOURS = {
    Status.NEW: 2,
    Status.OPEN: 6,
    Status.IN_PROGRESS: 12,
    Status.REOPENED: 4
}

def is_valid_status_transition(old_status: Status, new_status: Status) -> bool:
    match(old_status):
        case Status.NEW:
            if new_status == Status.OPEN: return True
            return False
        case Status.OPEN:
            if new_status == Status.IN_PROGRESS: return True
            return False
        case Status.IN_PROGRESS:
            if new_status == Status.PENDING or Status.ON_HOLD or Status.RESOLVED: return True
            return False
        case Status.PENDING:
            if new_status == Status.IN_PROGRESS or new_status == Status.RESOLVED: return True
        case Status.ON_HOLD:
            if new_status == Status.IN_PROGRESS: return True
        case Status.RESOLVED:
            if new_status == Status.CLOSED or new_status == Status.REOPENED: return True
            return False
        case Status.REOPENED:
            if new_status == Status.IN_PROGRESS: return True
            return False
    return False