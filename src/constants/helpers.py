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
