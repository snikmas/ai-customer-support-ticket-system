from datetime import datetime, timezone
from .permissions import check_for_access
from src import constants
from src import models as api_models
from src.db import models as db_models, operations
from src.exceptions.domain import (
    AlreadyDeletedError,
    AuditLogError,
    AuthorizationError,
    EmptyUpdateError,
    InternalOperationError,
    InvalidAssigneeError,
    TicketAlreadyAssignedError,
    TicketDeletedError,
    TicketNotFoundError,
    TicketStatusConflictError,
    UserNotFoundError,
)
from src.cache import check_ticket, cache_ticket
import json

def _to_api_ticket(ticket: db_models.Ticket) -> api_models.Ticket:
    if ticket.tags is None or isinstance(ticket.tags, str):
        ticket.tags = constants.deserialize_tags(ticket.tags)
    return api_models.Ticket.model_validate(ticket, from_attributes=True)


def _can_read_ticket(ticket: db_models.Ticket, requester: api_models.User) -> bool:
    if requester.role in [constants.Role.ADMIN, constants.Role.SUPER_ADMIN]:
        return True
    if ticket.deleted_at is not None:
        return False
    if requester.role in [constants.Role.MANAGER, constants.Role.AGENT_READONLY]:
        return True
    if requester.role == constants.Role.AGENT:
        return (
            ticket.assigned_agent_id == requester.id
            or (
                ticket.assigned_agent_id is None
                and ticket.status == constants.Status.NEW
            )
        )
    if requester.role == constants.Role.USER:
        return ticket.creator_user_id == requester.id
    return False

def create_ticket(ticket_data: api_models.TicketCreate, requester: api_models.User) -> api_models.Ticket:
    now = datetime.now(timezone.utc)

    if (check_for_access(requester.role, constants.Role.USER)) is False:
        raise AuthorizationError()
    
    ticket = db_models.Ticket(
        id=constants.generate_id(),
        title=ticket_data.title,
        description=ticket_data.description,
        category=ticket_data.category,
        tags=constants.serialize_tags(ticket_data.tags),
        assigned_agent_id=None,
        creator_user_id=requester.id,
        status=constants.Status.NEW,
        priority=constants.Priority.NORMAL,
        updated_at=now,
        created_at=now,
        deleted_at=None
    )
    
    event = api_models.Event(
        id=constants.generate_id(),
        entity_type=constants.EntityType.TICKET,
        entity_id=ticket.id,
        actor_user_id=requester.id,
        event_type=constants.EventType.TICKET_CREATED,
        old_value=None,
        new_value=json.dumps({"ticket_id": ticket.id}), #?
        metadata=None,
        created_at=now
    )

    ticket = operations.create_ticket(ticket, event)

    return _to_api_ticket(ticket)


def get_ticket(id: str, requester: api_models.User) -> api_models.Ticket: #im not sure is it a db ticket or api model
    if check_for_access(requester.role, constants.Role.USER) is False:
        raise AuthorizationError()
    
    ticket = check_ticket(id)
    if ticket is None:
        ticket = operations.get_ticket(id)
    
    if ticket is None:
        raise TicketNotFoundError()

    cache_ticket(ticket)
    if _can_read_ticket(ticket, requester) is False:
        raise AuthorizationError()

    return _to_api_ticket(ticket)


def get_all_tickets(
        requester: api_models.User,
        limit: int,
        offset: int,
        sort_by: str,
        sort_order: str,
        priority: constants.Priority | None,
        status: constants.Status | None
        ) -> list[api_models.Ticket]:
    
    
    # Permission filtering must happen before pagination. Otherwise a page can
    # be short or empty simply because unauthorized rows occupied its DB slice.
    tickets = operations.get_tickets(None, 0, sort_by, sort_order, priority, status)
    visible_tickets = [ticket for ticket in tickets if _can_read_ticket(ticket, requester)]
    page = visible_tickets[offset:offset + limit]
    return [_to_api_ticket(ticket) for ticket in page]

def update_ticket(updated_info_id: str, updated_info: api_models.TicketUpdate, requester: api_models.User) -> api_models.Ticket:
    ticket = operations.get_ticket(updated_info_id)
    if ticket is None:
        raise TicketNotFoundError()
    if ticket.deleted_at is not None:
        raise TicketDeletedError()

    # ================= STANDARTIZATION PROCESS ========================
    #for audit logs, json friendly
    audit_new_info = updated_info.model_dump(exclude_unset=True, mode="json")
    # keeos python objects, for db
    updated_info = updated_info.model_dump(exclude_unset=True)

    if not updated_info or not audit_new_info:
        raise EmptyUpdateError()

    if 'tags' in updated_info and updated_info['tags'] is not None:
        updated_info['tags'] = constants.serialize_tags(updated_info['tags'])
        
    # =================================================================
    # ================= ACCESS PROCCESS ===============================
    
    requested_fields = set(updated_info.keys())

    if requester.role == constants.Role.USER:
        if ticket.creator_user_id != requester.id:
            raise AuthorizationError()
        allowed_fields = {"status", "tags"}
        if requested_fields - allowed_fields:
            raise AuthorizationError("ticket_fields_not_allowed")
        if "status" in requested_fields and updated_info["status"] not in [constants.Status.OPEN, constants.Status.CLOSED]:
            raise AuthorizationError("ticket_status_not_allowed")
        if "tags" in requested_fields and ticket.status != constants.Status.NEW:
            raise AuthorizationError("ticket_tags_locked_after_triage")
            
    elif requester.role == constants.Role.AGENT:
        allowed_fields = {"status", "tags"}

        if requested_fields - allowed_fields:
            raise AuthorizationError("ticket_fields_not_allowed")

        if ticket.assigned_agent_id != requester.id:
            raise AuthorizationError("ticket_not_assigned_to_requester")


    elif check_for_access(requester.role, constants.Role.MANAGER):
        allowed_fields = {
            "status",
            "assigned_agent_id",
            "priority",
            "tags",
            }
        if requested_fields - allowed_fields:
            raise AuthorizationError("ticket_fields_not_allowed")
    else:
        raise AuthorizationError()
    
    if 'assigned_agent_id' in updated_info:
        agent = operations.get_user(updated_info['assigned_agent_id'])
        if agent is None:
            raise InvalidAssigneeError("assignee_not_found")
        if agent.role not in [constants.Role.AGENT, constants.Role.MANAGER]:
            raise InvalidAssigneeError()


    if "status" in requested_fields:
        if constants.is_valid_status_transition(ticket.status, updated_info['status']) is False:
            raise TicketStatusConflictError()
        
    
    old_info = {}
    for field in updated_info:
        old_value = getattr(ticket, field)

        if field == 'tags':
            old_info[field] = [tag.value for tag in constants.deserialize_tags(old_value)]
        elif hasattr(old_value, 'value'):
            old_info[field] = old_value.value
        else:
            old_info[field] = old_value

    event = api_models.Event(
        id=constants.generate_id(),
        entity_type=constants.EntityType.TICKET,
        entity_id=ticket.id,
        actor_user_id=requester.id,
        event_type=constants.EventType.TICKET_UPDATED,
        old_value=json.dumps(old_info),
        new_value=json.dumps(audit_new_info),
        metadata=None,
        created_at=datetime.now(timezone.utc)
    )

    # if status in updates (even with a few fields) -> still status changed
    if 'status' in updated_info.keys():
        event.event_type = constants.EventType.TICKET_STATUS_CHANGED

    ticket = operations.update_ticket(updated_info_id, updated_info, event)

    if ticket is None:
        raise InternalOperationError("ticket_update_failed")
    
    return _to_api_ticket(ticket)

def delete_ticket(id: str, requester: api_models.User, batch_info: str | None = None) -> None:
    ticket = operations.get_ticket(id)

    if ticket is None:
        raise TicketNotFoundError()
    if ticket.deleted_at is not None:
        raise AlreadyDeletedError()

    if ticket.creator_user_id != requester.id:
        if check_for_access(requester.role, constants.Role.ADMIN) is False: 
            raise AuthorizationError()

    now = datetime.now(timezone.utc)
    delete_info = {
        "deleted_at": now,
        "updated_at": now,
    }
    
    event = api_models.Event(
        id=constants.generate_id(),
        entity_type=constants.EntityType.TICKET,
        entity_id=ticket.id,
        actor_user_id=requester.id,
        event_type=constants.EventType.TICKET_DELETED,
        old_value=constants._audit_json({"deleted_at": ticket.deleted_at, "updated_at": ticket.updated_at}),
        new_value=constants._audit_json(delete_info),
        metadata=None,
        created_at=now,
        batch_id=batch_info
    )



    if operations.delete_ticket(id, delete_info, event) is False:
        raise InternalOperationError("ticket_delete_failed")
    

def delete_all_tickets(requester: api_models.User) -> int:
    user = operations.get_user(requester.id)
    if user is None:
        raise UserNotFoundError()
    
    if check_for_access(user.role, constants.Role.SUPER_ADMIN) is False:
        raise AuthorizationError()
    
    all_tickets = operations.get_tickets()
    now = datetime.now(timezone.utc)
    event = api_models.Event(
        id=constants.generate_id(),
        entity_type=constants.EntityType.TICKET,
        entity_id=None,
        actor_user_id=requester.id,
        event_type=constants.EventType.TICKETS_BULK_DELETED,
        old_value=constants._audit_json({"deleted_at": None}),
        new_value=constants._audit_json({"deleted_at": now}), # do we need change status? for closed?
        metadata=None,
        created_at=now,
        batch_id=constants.generate_id()
    )

    events = [event]
    if all_tickets:
        for ticket in all_tickets:
            if ticket.deleted_at is None:
                event_ticket = api_models.Event(
                    id=constants.generate_id(),
                    entity_type=constants.EntityType.TICKET,
                    entity_id=ticket.id,
                    actor_user_id=requester.id,
                    event_type=constants.EventType.TICKET_DELETED,
                    old_value=constants._audit_json({"deleted_at": None}),
                    new_value=constants._audit_json({"deleted_at": now}), # do we need change status? for closed?
                    metadata=None,
                    created_at=now,
                    batch_id=event.batch_id
                )
                events.append(event_ticket)

    return operations.delete_all_tickets(events)


def claim_ticket(ticket_id: str, requester: api_models.User) -> api_models.Ticket | None:
    ticket = operations.get_ticket(ticket_id)
    
    if ticket is None:
        raise TicketNotFoundError()
    
    if check_for_access(requester.role, constants.Role.AGENT) is False:
        raise AuthorizationError("only_agents_can_claim")
    
    if ticket.deleted_at is not None:
        raise TicketDeletedError()
    
    if ticket.assigned_agent_id is not None:
        raise TicketAlreadyAssignedError()
    
    if ticket.status != constants.Status.NEW:
        raise TicketStatusConflictError("ticket_not_new")
    

    event = api_models.Event(
        id=constants.generate_id(),
        entity_type=constants.EntityType.TICKET,
        entity_id=ticket.id,
        actor_user_id=requester.id,
        event_type=constants.EventType.TICKET_CLAIMED,
        old_value=json.dumps({"ticket_status": constants.Status.NEW.value}),
        new_value=json.dumps({"ticket_status": constants.Status.IN_PROGRESS.value}),
        metadata=None,
        created_at=datetime.now(timezone.utc)
    )
    
    res = operations.claim_ticket(ticket_id, requester.id, event)
    if res is None:
        raise TicketAlreadyAssignedError()
    
    return _to_api_ticket(res)


def assign_ticket(ticket_id: str, agent_id: str, requester: api_models.User) -> api_models.Ticket | None:
    ticket = operations.get_ticket(ticket_id)


    if ticket is None:
        raise TicketNotFoundError()
    if ticket.deleted_at is not None:
        raise TicketDeletedError()
    is_reassign = False
    if ticket.assigned_agent_id is not None:
        is_reassign = True
    
    agent = operations.get_user(agent_id)
    if agent is None:
        raise InvalidAssigneeError("assignee_not_found")
    
    if check_for_access(requester.role, constants.Role.MANAGER) is False:
        raise AuthorizationError()

    if agent.role != constants.Role.AGENT:
        raise InvalidAssigneeError("assignee_must_be_agent")

    event = api_models.Event(
       id=constants.generate_id(),
       entity_type=constants.EntityType.TICKET,
       entity_id=ticket.id,
       actor_user_id=requester.id,
       event_type=constants.EventType.TICKET_ASSIGNED,
       old_value=json.dumps({"ticket.status": constants.Status.NEW.value, "assigned_agent_id": None}),
       new_value=json.dumps({"ticket.status": constants.Status.IN_PROGRESS.value, "assigned_agent_id": agent_id}),
       metadata=None,
       created_at=datetime.now(timezone.utc)
    )   

    if is_reassign:
        event.event_type = constants.EventType.TICKET_REASSIGNED

    res = operations.assign_ticket(ticket.id, agent.id, event)
    if res is None:
        raise InternalOperationError("ticket_assignment_failed")

    return _to_api_ticket(res)
