from datetime import datetime
from .permissions import check_for_access
from src import constants
from src.models import models as api_models
from src.db import models as db_models
from src.db import operations



def create_user(user_data: api_models.UserCreate, requester_user: api_models.User) -> db_models.User:
    now = datetime.now()

    user = db_models.User(
        id=constants.generate_id(),
        nickname=user_data.nickname,
        avatar_url=user_data.avatar_url,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        phone=user_data.phone,
        email=user_data.email,
        role=constants.Role.USER, #? the system after can update the role for agents/etc? how does it work in a big tech companies
        updated_at=now,
        created_at=now
    )
    operations.create_user(user)
    return user

def get_user(id: str, requester_user: api_models.User) -> db_models.User | None:
    if check_for_access(requester_user, constants.Role.USER) is False:
        return None
    
    return operations.get_user(id)

def get_all_users(requester_user: api_models.User) -> list[db_models.User] | None:
    if check_for_access(requester_user, constants.Role.MANAGER) is False:
        return None

    return operations.get_users()

def update_user(updated_info_id: str, updated_info: api_models.UserUpdate, requester: api_models.User) -> db_models.User:

    if not updated_info: return None

    user = operations.get_user(requester.id)
    if user is None:
        return None #user not found

    updated_info = updated_info.model_dump(exclude_unset=True)

    if user.id != updated_info_id or 'role' in updated_info.keys():
        if check_for_access(user, constants.Role.ADMIN) is False:
            return None

    return operations.update_user(id, updated_info)


def delete_user(id: str, reqiester_user: api_models.User) -> db_models.User:
    user = operations.get_user(reqiester_user.id) # if its exist?

    if user is None: return None

    if user.id != id:
        if check_for_access(user, constants.Role.ADMIN) is False: 
            return None
    
    return operations.delete_user(id)


def delete_all_users(requester: api_models.User) -> db_models.User:
    user = operations.get_user(requester.id)

    if user is None:
        return None
    
    if check_for_access(user, constants.Role.SUPER_ADMIN) is False:
        return None
    
    return operations.delete_all_users()