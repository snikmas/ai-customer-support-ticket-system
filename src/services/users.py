from datetime import datetime, timezone
from .permissions import check_for_access
from src import constants
from src import models as api_models
from src.db import models as db_models
from src.db import operations
from src.core import hash_password
from src.exceptions.domain import (
    AgentDepartmentChangeConflictError,
    AuthorizationError,
    AgentProfileNotFoundError,
    EmptyUpdateError,
    InactiveRoutingCatalogError,
    InternalOperationError,
    UserAlreadyExistsError,
    UserNotFoundError,
    LastSuperAdminError,
    FinalAdminAccessError,
)
from src.services.routing import dispatch_waiting_tickets_after_capacity_event
from sqlalchemy.exc import IntegrityError
import json


PROFILE_MANAGER_ROLES = {
    constants.Role.MANAGER,
    constants.Role.ADMIN,
    constants.Role.SUPER_ADMIN,
}


def _load_agent_profile_context(
    agent_id: str,
    requester: api_models.User,
) -> tuple[db_models.User, db_models.User, db_models.AgentProfile]:
    stored_requester = operations.get_user(requester.id)
    if stored_requester is None:
        raise UserNotFoundError()

    agent = operations.get_user(agent_id)
    if agent is None or agent.role is not constants.Role.AGENT:
        raise AgentProfileNotFoundError()

    profile = operations.get_agent_profile(agent_id)
    if profile is None:
        raise AgentProfileNotFoundError()

    return stored_requester, agent, profile


def _agent_profile_response(
    agent: db_models.User,
    profile: db_models.AgentProfile,
) -> api_models.AgentProfileResponse:
    current_workload = operations.count_active_assigned_tickets(agent.id)
    can_receive_new_tickets = _can_agent_receive_new_tickets(
        agent,
        profile,
        current_workload,
    )
    return api_models.AgentProfileResponse(
        user_id=profile.user_id,
        availability_status=profile.availability_status,
        availability_reason=profile.availability_reason,
        availability_note=profile.availability_note,
        unavailable_until=profile.unavailable_until,
        max_active_tickets=profile.max_active_tickets,
        last_assigned_at=profile.last_assigned_at,
        department_id=profile.department_id,
        skill_ids=profile.skill_ids,
        current_active_tickets=current_workload,
        can_receive_new_tickets=can_receive_new_tickets,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def _can_agent_receive_new_tickets(
    agent: db_models.User,
    profile: db_models.AgentProfile,
    current_workload: int,
) -> bool:
    return (
        agent.role is constants.Role.AGENT
        and agent.user_status is constants.UserStatus.ACTIVE
        and agent.deleted_at is None
        and profile.availability_status is constants.AvailabilityStatus.AVAILABLE
        and profile.department_id is not None
        and operations.get_routing_catalog_record(
            db_models.Department,
            profile.department_id,
        ) is not None
        and current_workload < profile.max_active_tickets
    )


def get_agent_profile_settings(
    agent_id: str,
    requester: api_models.User,
) -> api_models.AgentProfileResponse:
    stored_requester, agent, profile = _load_agent_profile_context(agent_id, requester)
    if stored_requester.id != agent_id and stored_requester.role not in PROFILE_MANAGER_ROLES:
        raise AuthorizationError()
    return _agent_profile_response(agent, profile)


def update_agent_availability(
    agent_id: str,
    update_data: api_models.AgentAvailabilityUpdate,
    requester: api_models.User,
) -> api_models.AgentProfileResponse:
    stored_requester, agent, profile = _load_agent_profile_context(agent_id, requester)
    if stored_requester.id != agent_id and stored_requester.role not in PROFILE_MANAGER_ROLES:
        raise AuthorizationError()

    old_availability_status = profile.availability_status
    current_workload = operations.count_active_assigned_tickets(agent.id)
    was_eligible = _can_agent_receive_new_tickets(
        agent,
        profile,
        current_workload,
    )
    now = datetime.now(timezone.utc)
    new_info = {
        "availability_status": update_data.availability_status,
        "availability_reason": (
            update_data.reason.value if update_data.reason is not None else None
        ),
        "availability_note": update_data.note,
        "unavailable_until": update_data.unavailable_until,
        "updated_at": now,
    }
    if update_data.availability_status is constants.AvailabilityStatus.AVAILABLE:
        new_info.update(
            availability_reason=None,
            availability_note=None,
            unavailable_until=None,
        )

    old_info = {
        "availability_status": profile.availability_status,
        "availability_reason": profile.availability_reason,
        "availability_note": profile.availability_note,
        "unavailable_until": profile.unavailable_until,
    }
    event = api_models.Event(
        id=constants.generate_id(),
        entity_type=constants.EntityType.AGENT_PROFILE,
        entity_id=agent_id,
        actor_user_id=stored_requester.id,
        event_type=constants.EventType.AGENT_AVAILABILITY_CHANGED,
        old_value=constants._audit_json(old_info),
        new_value=constants._audit_json(new_info),
        metadata=None,
        created_at=now,
    )
    updated_profile = operations.update_agent_profile(agent_id, new_info, event)
    if updated_profile is None:
        raise AgentProfileNotFoundError()
    response = _agent_profile_response(agent, updated_profile)
    became_available = (
        old_availability_status is not constants.AvailabilityStatus.AVAILABLE
        and updated_profile.availability_status
        is constants.AvailabilityStatus.AVAILABLE
    )
    if became_available or (
        not was_eligible and response.can_receive_new_tickets
    ):
        dispatch_waiting_tickets_after_capacity_event(
            "agent_became_available",
            agent_id,
        )
    return response


def update_agent_profile_settings(
    agent_id: str,
    update_data: api_models.AgentProfileManagementUpdate,
    requester: api_models.User,
) -> api_models.AgentProfileResponse:
    stored_requester, agent, profile = _load_agent_profile_context(agent_id, requester)
    if stored_requester.role not in PROFILE_MANAGER_ROLES:
        raise AuthorizationError()

    current_workload = operations.count_active_assigned_tickets(agent.id)
    was_eligible = _can_agent_receive_new_tickets(
        agent,
        profile,
        current_workload,
    )
    old_max_active_tickets = profile.max_active_tickets
    new_info = update_data.model_dump(exclude_unset=True)
    if not new_info:
        raise EmptyUpdateError()

    routing_metadata_changed = bool({"department_id", "skill_ids"} & new_info.keys())
    if "skill_ids" in new_info and new_info["skill_ids"] is None:
        raise InactiveRoutingCatalogError("Agent skill IDs must be a list")
    if "department_id" in new_info:
        if new_info["department_id"] is None:
            raise InactiveRoutingCatalogError("An agent department must be active")
        if (
            new_info["department_id"] != profile.department_id
            and current_workload > 0
        ):
            raise AgentDepartmentChangeConflictError()

    requested_skill_ids = new_info.get("skill_ids", profile.skill_ids)
    requested_department_id = new_info.get("department_id", profile.department_id)
    department, active_skills = operations.active_routing_catalog_selection(
        requested_department_id,
        requested_skill_ids,
    )
    if requested_department_id is not None and department is None:
        raise InactiveRoutingCatalogError("Agent department is missing or archived")
    if len(active_skills) != len(requested_skill_ids):
        raise InactiveRoutingCatalogError("One or more agent skills are missing or archived")

    old_info = {}
    for field in new_info:
        old_info[field] = (
            list(profile.skill_ids)
            if field == "skill_ids"
            else constants._audit_value(getattr(profile, field))
        )
    now = datetime.now(timezone.utc)
    new_info["updated_at"] = now
    event = api_models.Event(
        id=constants.generate_id(),
        entity_type=constants.EntityType.AGENT_PROFILE,
        entity_id=agent_id,
        actor_user_id=stored_requester.id,
        event_type=constants.EventType.AGENT_PROFILE_UPDATED,
        old_value=constants._audit_json(old_info),
        new_value=constants._audit_json(new_info),
        metadata=None,
        created_at=now,
    )
    updated_profile = operations.update_agent_profile(agent_id, new_info, event)
    if updated_profile is None:
        raise AgentProfileNotFoundError()
    response = _agent_profile_response(agent, updated_profile)
    capacity_increased = (
        updated_profile.max_active_tickets > old_max_active_tickets
    )
    if routing_metadata_changed or capacity_increased or (
        not was_eligible and response.can_receive_new_tickets
    ):
        dispatch_waiting_tickets_after_capacity_event(
            "agent_capacity_increased",
            agent_id,
        )
    return response



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


def create_staff_user(
    user_data: api_models.StaffCreate,
    requester: api_models.User,
) -> db_models.User:
    if requester.role not in {
        constants.Role.ADMIN,
        constants.Role.SUPER_ADMIN,
    }:
        raise AuthorizationError()
    department, active_skills = operations.active_routing_catalog_selection(
        user_data.department_id,
        user_data.skill_ids,
    )
    if user_data.role is constants.Role.AGENT:
        if user_data.department_id is not None and department is None:
            raise InactiveRoutingCatalogError(
                "Agent department is missing or archived"
            )
        if len(active_skills) != len(user_data.skill_ids):
            raise InactiveRoutingCatalogError(
                "One or more agent skills are missing or archived"
            )
    now = datetime.now(timezone.utc)
    user = db_models.User(
        id=constants.generate_id(),
        nickname=user_data.nickname,
        avatar_url=user_data.avatar_url,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        phone=user_data.phone,
        email=user_data.email,
        password=hash_password(user_data.password),
        role=user_data.role,
        updated_at=now,
        created_at=now,
        deleted_at=None,
        user_status=constants.UserStatus.ACTIVE,
    )
    event = api_models.Event(
        id=constants.generate_id(),
        entity_type=constants.EntityType.USER,
        entity_id=user.id,
        actor_user_id=requester.id,
        event_type=constants.EventType.USER_CREATED,
        old_value=None,
        new_value=constants._audit_json({"id": user.id, "role": user.role}),
        metadata="source=staff_creation",
        created_at=now,
    )
    try:
        return operations.create_staff_user(
            user,
            event,
            max_active_tickets=user_data.max_active_tickets,
            department_id=user_data.department_id,
            skill_ids=user_data.skill_ids,
        )
    except IntegrityError as exc:
        raise UserAlreadyExistsError() from exc


def bootstrap_superadmin(user_data: api_models.UserCreate) -> bool:
    now = datetime.now(timezone.utc)
    user = db_models.User(
        id=constants.generate_id(),
        nickname=user_data.nickname,
        avatar_url=user_data.avatar_url,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        phone=user_data.phone,
        email=user_data.email,
        password=hash_password(user_data.password),
        role=constants.Role.SUPER_ADMIN,
        updated_at=now,
        created_at=now,
    )
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
        created_at=now,
    )
    return operations.create_initial_superadmin(user, event)

def get_user(id: str, requester: api_models.User) -> db_models.User:
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
                  sort_order: str,
                  *,
                  role: constants.Role | None = None,
                  user_status: constants.UserStatus | None = None,
                  search: str | None = None,
                  ) -> list[db_models.User]:
    if check_for_access(requester.role, constants.Role.MANAGER) is False:
        raise AuthorizationError()

    return operations.get_users(
        limit,
        offset,
        sort_by,
        sort_order,
        role=role,
        user_status=user_status,
        search=search,
    )

def update_user(updated_info_id: str, updated_info: api_models.UserUpdate, requester: api_models.User) -> db_models.User:
    requester = operations.get_user(requester.id)
    if requester is None:
        raise UserNotFoundError()
    
    user = operations.get_user(updated_info_id)
    if user is None:
        raise UserNotFoundError()

    audit_new_info = updated_info.model_dump(exclude_unset=True, mode="json")
    updated_info = updated_info.model_dump(exclude_unset=True)
    if not updated_info:
        raise EmptyUpdateError()
    routing_eligibility_may_change = bool(
        {"role", "user_status"} & updated_info.keys()
    )
    old_role = user.role
    old_profile = (
        operations.get_agent_profile(user.id)
        if routing_eligibility_may_change
        else None
    )
    was_eligible = (
        old_profile is not None
        and _can_agent_receive_new_tickets(
            user,
            old_profile,
            operations.count_active_assigned_tickets(user.id),
        )
    )

    if any(key in updated_info for key in ['updated_at', 'created_at']): return None #no one can change it
    if requester.id != updated_info_id:
        if check_for_access(requester.role, constants.Role.ADMIN) is False:
            raise AuthorizationError()

    if any(key in updated_info for key in ['role', 'user_status', 'deleted_at']):
        if check_for_access(requester.role, constants.Role.ADMIN) is False:
            raise AuthorizationError()

    role_removes_super_admin = (
        user.role is constants.Role.SUPER_ADMIN
        and (
            updated_info.get("role", user.role) is not constants.Role.SUPER_ADMIN
            or updated_info.get("user_status", user.user_status) is not constants.UserStatus.ACTIVE
            or updated_info.get("deleted_at", user.deleted_at) is not None
        )
    )
    if role_removes_super_admin:
        if requester.role is not constants.Role.SUPER_ADMIN and requester.id != user.id:
            raise AuthorizationError(
                "Only a Super Admin can manage another Super Admin",
                code="super_admin_management_forbidden",
            )
        if operations.count_active_superadmins() <= 1:
            raise LastSuperAdminError()

    removes_requester_admin_access = (
        requester.id == user.id
        and user.role in {constants.Role.ADMIN, constants.Role.SUPER_ADMIN}
        and (
            updated_info.get("role", user.role) not in {constants.Role.ADMIN, constants.Role.SUPER_ADMIN}
            or updated_info.get("user_status", user.user_status) is not constants.UserStatus.ACTIVE
            or updated_info.get("deleted_at", user.deleted_at) is not None
        )
    )
    if removes_requester_admin_access and operations.count_active_administrators() <= 1:
        raise FinalAdminAccessError()

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
        raise InternalOperationError("User could not be updated", code="user_update_failed")

    if routing_eligibility_may_change:
        updated_profile = operations.get_agent_profile(user.id)
        is_eligible = (
            updated_profile is not None
            and _can_agent_receive_new_tickets(
                user,
                updated_profile,
                operations.count_active_assigned_tickets(user.id),
            )
        )
        is_user_to_agent_promotion = (
            old_role is constants.Role.USER
            and user.role is constants.Role.AGENT
        )
        if not was_eligible and is_eligible and not is_user_to_agent_promotion:
            dispatch_waiting_tickets_after_capacity_event(
                "agent_became_eligible",
                user.id,
            )

    return user

def delete_user(id: str, requester_user: api_models.User) -> None:
    requester = operations.get_user(requester_user.id)

    if requester is None:
        raise UserNotFoundError()
    
    user = operations.get_user(id)
    if user is None:
        raise UserNotFoundError()

    if requester.id != id:
        if check_for_access(requester.role, constants.Role.ADMIN) is False: 
            raise AuthorizationError()
    
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
        raise InternalOperationError("User could not be deleted", code="user_delete_failed")


def delete_all_users(requester: api_models.User) -> int:
    requester = operations.get_user(requester.id)
    if requester is None:
        raise UserNotFoundError()
    
    if check_for_access(requester.role, constants.Role.SUPER_ADMIN) is False:
        raise AuthorizationError()


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
