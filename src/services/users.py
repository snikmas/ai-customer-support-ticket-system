from datetime import datetime, timezone
from .permissions import check_for_access
from src import constants
from src import models as api_models
from src.db import models as db_models
from src.db import operations
from src.core import hash_password
from src.exceptions.domain import AuthorizationError, UserNotFoundError
from src.exceptions.domain import UserAlreadyExistsError
from sqlalchemy.exc import IntegrityError
import json



def create_user(user_data: api_models.UserCreate) -> db_models.User:
    now = datetime.now(timezone.utc)

    user = db_models.User(
        id=constants.generate_id(),
        nickname=user_data.nickname,
        avatar_url=user_data.avatar_url,
        first_name=user_data.first_name, 
        last_name=user_data.last_name,
        phone=user_data.phone,
        email=user_data.email,
        password = hash_password(user_data.password),
        role=constants.Role.USER, #? the system after can update the role for agents/etc? how does it work in a big tech companies
        updated_at=now,
        created_at=now
    )
    if len(operations.get_users()) == 0:
        user.role = constants.Role.SUPER_ADMIN

    
    event = api_models.Event(
        id=constants.generate_id(),
        entity_type=constants.EntityType.USER,
        entity_id=user.id,
        actor_user_id=user.id,
        event_type=constants.EventType.USER_CREATED,
        old_value=None,
        new_value=constants._audit_json({
            "id": user.id,
            "nickname": user.nickname,
            "role": user.role,
            "user_status": constants.UserStatus.ACTIVE,
        }),
        metadata=None,
        created_at=now
    )

    try:
        operations.create_user(user, event)
    except IntegrityError as exc:
        raise UserAlreadyExistsError() from exc

    return user

def get_user(id: str, requester: api_models.User) -> db_models.User: #im not sure is it a db user or api model
    if requester.id != id and check_for_access(requester.role, constants.Role.ADMIN) is False:
        raise AuthorizationError()

    user = operations.get_user(id)
    if user is None:
        raise UserNotFoundError()
    
    if user.user_status != constants.UserStatus.ACTIVE and requester.role not in [constants.Role.ADMIN, constants.Role.SUPER_ADMIN]:
        raise UserNotFoundError()
    
    return user

def get_all_users(requester: api_models.User,
                  limit: int,
                  offset: int,
                  sort_by: str,
                  sort_order: str) -> list[db_models.User]:
    if check_for_access(requester.role, constants.Role.MANAGER) is False:
        raise PermissionError

    return operations.get_users(limit, offset, sort_by, sort_order)

def update_user(updated_info_id: str, updated_info: api_models.UserUpdate, requester: api_models.User) -> db_models.User:
    requester = operations.get_user(requester.id)
    if requester is None:
        raise ValueError("user_not_found")
    
    user = operations.get_user(updated_info_id)
    if user is None:
        raise ValueError("user_not_found")

    audit_new_info = updated_info.model_dump(exclude_unset=True, mode="json")
    updated_info = updated_info.model_dump(exclude_unset=True)
    if not updated_info:
        raise ValueError("empty_update")

    if any(key in updated_info for key in ['updated_at', 'created_at']): return None #no one can change it
    if requester.id != updated_info_id:
        if check_for_access(requester.role, constants.Role.ADMIN) is False:
            raise PermissionError

    if any(key in updated_info for key in ['role', 'user_status', 'deleted_at']):
        if check_for_access(requester.role, constants.Role.ADMIN) is False:
            raise PermissionError

    if 'password' in updated_info:
        updated_info['password'] = hash_password(updated_info['password'])
        audit_new_info['password'] = "<changed>"

    old_info = {}
    for field in updated_info:
        if field == 'password':
            old_info[field] = "<changed>"
        else:
            old_info[field] = constants._audit_value(getattr(user, field))
    updated_info['updated_at'] = datetime.now(timezone.utc)

    event = api_models.Event(
        id=constants.generate_id(),
        entity_type=constants.EntityType.USER,
        entity_id=user.id,
        actor_user_id=requester.id,
        event_type=constants.EventType.USER_UPDATED,
        old_value=constants._audit_json(old_info),
        new_value=json.dumps(audit_new_info),
        metadata=None,
        created_at=datetime.now(timezone.utc)
    )

    user = operations.update_user(updated_info_id, updated_info, event)
    if user is None:
        raise ValueError("Some error during updating, the operation canceled")

    return user

def delete_user(id: str, reqiester_user: api_models.User) -> None:
    requester = operations.get_user(reqiester_user.id) # if its exist?

    if requester is None:
        raise ValueError("user_not_found")
    
    user = operations.get_user(id)
    if user is None:
        raise ValueError("user_not_found")

    if requester.id != id:
        if check_for_access(requester.role, constants.Role.ADMIN) is False: 
            raise PermissionError
    
    now = datetime.now(timezone.utc)
    old_data = {'deleted_at': user.deleted_at, 'updated_at': user.updated_at, 'user_status': user.user_status}
    delete_info = {'deleted_at': now, "updated_at": now, 'user_status': constants.UserStatus.DELETED}
    event = api_models.Event(
        id=constants.generate_id(),
        entity_type=constants.EntityType.USER,
        entity_id=user.id,
        actor_user_id=requester.id,
        event_type=constants.EventType.USER_DELETED,
        old_value=constants._audit_json(old_data),
        new_value=constants._audit_json(delete_info),
        metadata=None,
        created_at=now
    )

    if operations.delete_user(id, delete_info, event) is not True:
        raise ValueError("Some error during deleting, the operation cancelled")


def delete_all_users(requester: api_models.User) -> int:
    requester = operations.get_user(requester.id)
    if requester is None:
        raise ValueError("user_not_found")
    
    if check_for_access(requester.role, constants.Role.SUPER_ADMIN) is False:
        raise PermissionError


    users = operations.get_users()
    now = datetime.now(timezone.utc)

    event = api_models.Event(
        id=constants.generate_id(),
        entity_type=constants.EntityType.USER,
        entity_id=None,
        actor_user_id=requester.id,
        event_type=constants.EventType.USER_BULK_DELETED,
        old_value=constants._audit_json({"deleted_at": None}),
        new_value=constants._audit_json({"deleted_at": now}), # do we need change status? for closed?
        metadata=None,
        created_at=now,
        batch_id=constants.generate_id()
    )
    
    events = [event]
    if users:
        for user in users:
            if user.user_status is not constants.UserStatus.DELETED:
                event_user = api_models.Event(
                    id=constants.generate_id(),
                    entity_type=constants.EntityType.USER,
                    entity_id=user.id,
                    actor_user_id=requester.id,
                    event_type=constants.EventType.USER_DELETED,
                    old_value=constants._audit_json({"deleted_at": None}),
                    new_value=constants._audit_json({"deleted_at": now}), # do we need change status? for closed?
                    metadata=None,
                    created_at=now,
                    batch_id=event.batch_id
                )
                events.append(event_user)

    return operations.delete_all_users(events)
