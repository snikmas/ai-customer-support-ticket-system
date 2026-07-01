from datetime import datetime
from .permissions import check_for_access
from src import constants
from src.models import models as api_models
from src.db import models as db_models
from src.db import operations

def create_user(user_data: api_models.UserCreate) -> db_models.User:
    now = datetime.now()

    #check if the system is empty. if its - create an admin
        
    user = db_models.User(
        id=constants.generate_id(),
        nickname=user_data.nickname,
        avatar_url=user_data.avatar_url,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        phone=user_data.phone,
        email=user_data.email,
        password = user_data.password,
        role=constants.Role.USER, #? the system after can update the role for agents/etc? how does it work in a big tech companies
        updated_at=now,
        created_at=now
    )
    if len(operations.get_users()) == 0:
        user.role = constants.Role.SUPER_ADMIN

    operations.create_user(user)
    return user

def get_user(id: str, requester: api_models.User) -> db_models.User: #im not sure is it a db user or api model
    if check_for_access(requester.role, constants.Role.USER) is False:
        raise PermissionError
    
    user = operations.get_user(id)
    if user is None:
        raise ValueError("user_not_found")
    
    return user

def get_all_users(requester: api_models.User) -> list[db_models.User]:
    if check_for_access(requester.role, constants.Role.MANAGER) is False:
        raise PermissionError

    return operations.get_users()

def update_user(updated_info_id: str, updated_info: api_models.UserUpdate, requester: api_models.User) -> db_models.User:
    user = operations.get_user(requester.id)
    if user is None:
        raise ValueError("user_not_found")

    updated_info = updated_info.model_dump(exclude_unset=True)
    if not updated_info:
        raise ValueError("empty_update")

    if 'role' in updated_info.keys():
        updated_info['role'] = constants.Role[updated_info['role'].lower()]
        if user.id != updated_info_id:
            if check_for_access(user.role, constants.Role.ADMIN) is False:
                raise PermissionError

    res = operations.update_user(updated_info_id, updated_info)
    if res is None:
        raise ValueError("Some error during updating, the operation canceled")
    return res

def delete_user(id: str, reqiester_user: api_models.User) -> None:
    user = operations.get_user(reqiester_user.id) # if its exist?

    if user is None:
        raise ValueError("user_not_found")

    if user.id != id:
        if check_for_access(user.role, constants.Role.ADMIN) is False: 
            raise PermissionError
    
    if operations.delete_user(id) is not True:
        raise ValueError("Some error during deleting, the operation cancelled")


def delete_all_users(requester: api_models.User) -> int:
    requester = operations.get_user(requester.id)
    if requester is None:
        raise ValueError("user_not_found")
    
    if check_for_access(requester.role, constants.Role.SUPER_ADMIN) is False:
        raise PermissionError
    
    deleted_users = operations.delete_all_users()
    return deleted_users
