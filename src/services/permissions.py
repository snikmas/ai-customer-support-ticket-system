
from src import constants

def check_for_access(user_role: constants.Role, needed_rights: constants.Role) -> bool:
    return constants.ROLE_LEVELS[user_role] >= constants.ROLE_LEVELS[needed_rights]

