
from src import constants

def check_for_access(user_role: constants.Role, needed_rights: constants.Role) -> bool:
    return constants.ROLE_LEVELS[user_role] >= constants.ROLE_LEVELS[needed_rights]


def can_write_ticket_content(role: constants.Role) -> bool:
    """Whether a role may create/update/delete ticket content.

    Numeric role levels cannot express "view but not modify": AGENT_READONLY
    outranks USER yet must never write. This gate covers comments, attachments,
    and whole tickets, including tickets a read-only user originally created.
    """
    return (
        role != constants.Role.AGENT_READONLY
        and check_for_access(role, constants.Role.USER)
    )

