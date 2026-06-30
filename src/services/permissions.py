from datetime import datetime

from src import constants
from src.models import models as api_models
from src.db import models as db_models
from src.db import operations


def check_for_access(user: api_models.User, needed_rights: constants.Role) -> bool:
    return constants.ROLE_LEVELS[user.role] >= constants.ROLE_LEVELS[needed_rights]


