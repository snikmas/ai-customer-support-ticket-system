from datetime import datetime

from src import constants
from src.models import models as api_models

def check_for_access(user_role: api_models.User, needed_rights: constants.Role) -> bool:
    return constants.ROLE_LEVELS[user_role] >= constants.ROLE_LEVELS[needed_rights]


