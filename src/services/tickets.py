from datetime import datetime, timezone
import inspect
from sqlalchemy.exc import IntegrityError
from .permissions import check_for_access
from src import constants
from src import models as api_models
from src.db import models as db_models, operations
from src.exceptions.domain import (
    AlreadyDeletedError,
    AuditLogError,
    AuthorizationError,
    EmptyUpdateError,
    InactiveRoutingCatalogError,
    InternalOperationError,
    InvalidAssigneeError,
    TicketAlreadyAssignedError,
    TicketDeletedError,
    TicketNotFoundError,
    TicketStartWorkConflictError,
    TicketStatusConflictError,
    UserNotFoundError,
    RelatedTicketConflictError,
    RelatedTicketNotFoundError,
)
from src.cache import check_ticket as check_cached_ticket, cache_ticket, delete_ticket as delete_cached_ticket
from src.jobs import (
    enqueue_ticket_routing_job,
    get_job as jobs_get_job,
)
from src.services.routing import dispatch_waiting_tickets_after_capacity_event
from src.services import notifications as s_notifications
from src.constants import logger
import json

def _to_api_ticket(
    ticket: db_models.Ticket,
    *,
    now: datetime | None = None,
) -> api_models.Ticket:
    if ticket.tags is None or isinstance(ticket.tags, str):
        ticket.tags = constants.deserialize_tags(ticket.tags)
    response = api_models.Ticket.model_validate(ticket, from_attributes=True)
    return response.model_copy(update={
        "is_overdue": constants.is_ticket_overdue(
            response.due_at,
            now or constants.utc_now(),
        )
    })


def _validate_routing_catalog_selection(
    department_id: str | None,
    skill_ids: list[str],
) -> None:
    department, active_skills = operations.active_routing_catalog_selection(
        department_id,
        skill_ids,
    )
    if department is None:
        raise InactiveRoutingCatalogError("Ticket department is missing or archived")
    if len(active_skills) != len(skill_ids):
        raise InactiveRoutingCatalogError("One or more ticket skills are missing or archived")


def _require_same_active_department(
    ticket: db_models.Ticket,
    agent_id: str,
) -> None:
    profile = operations.get_agent_profile(agent_id)
    if profile is None or profile.department_id != ticket.department_id:
        raise InvalidAssigneeError(
            "Assignee must belong to the ticket department",
            code="assignee_department_mismatch",
        )
    department, _ = operations.active_routing_catalog_selection(
        profile.department_id,
        [],
    )
    if department is None:
        raise InvalidAssigneeError(
            "Assignee department is archived",
            code="assignee_department_inactive",
        )


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
    now = constants.utc_now()

    if (check_for_access(requester.role, constants.Role.USER)) is False:
        raise AuthorizationError()
    
    ticket = db_models.Ticket(
        id=constants.generate_id(),
        title=ticket_data.title,
        description=ticket_data.description,
        category=ticket_data.category,
        tags=constants.serialize_tags(ticket_data.tags),
        department_id=None,
        assigned_agent_id=None,
        creator_user_id=requester.id,
        status=constants.Status.NEW,
        priority=constants.Priority.NORMAL,
        updated_at=now,
        created_at=now,
        due_at=constants.calculate_sla_due_at(
            constants.Status.NEW,
            now,
            constants.Priority.NORMAL,
        ),
        deleted_at=None
    )
    
    event = api_models.Event(
        id=constants.generate_id(),
        entity_type=constants.EntityType.TICKET,
        entity_id=ticket.id,
        actor_user_id=requester.id,
        event_type=constants.EventType.TICKET_CREATED,
        old_value=None,
        new_value=constants._audit_json({
            "ticket_id": ticket.id,
            "status": ticket.status,
            "department_id": None,
            "skill_ids": [],
            "due_at": ticket.due_at,
        }),
        metadata=None,
        created_at=now
    )

    ticket = operations.create_ticket(ticket, event, [])
    return _to_api_ticket(ticket)


def get_ticket(id: str, requester: api_models.User) -> api_models.Ticket: #im not sure is it a db ticket or api model
    if check_for_access(requester.role, constants.Role.USER) is False:
        raise AuthorizationError()
    
    ticket = check_cached_ticket(id)
    if ticket is None:
        ticket = operations.get_ticket(id)
        if ticket is None:
            raise TicketNotFoundError()
        
        match requester.role:
            case constants.Role.USER:
                if ticket.creator_user_id != requester.id:
                    raise AuthorizationError()
            case constants.Role.AGENT:
                if ticket.creator_user_id != requester.id and ticket.assigned_agent_id != requester.id and ticket.status != constants.Status.NEW:
                    raise AuthorizationError()
            case constants.Role.MANAGER:
                if ticket.deleted_at is not None:
                    raise AuthorizationError()
            case constants.Role.AGENT_READONLY:
                if ticket.deleted_at is not None:
                    raise AuthorizationError()
        
        cache_ticket(_to_api_ticket(ticket))


    if _can_read_ticket(ticket, requester) is False:
        raise AuthorizationError()

    return _to_api_ticket(ticket)


def get_ticket_customer_summary(
    ticket_id: str,
    requester: api_models.User,
) -> api_models.TicketCustomerSummary:
    """Return only the requester needed to work on this ticket.

    This deliberately does not reuse the broad user-directory endpoint. An
    assigned agent, a manager+, or the ticket owner may see the limited
    summary; an unrelated agent cannot use a ticket id to enumerate customers.
    """
    ticket = operations.get_ticket(ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise TicketNotFoundError()

    is_manager = requester.role in {
        constants.Role.MANAGER,
        constants.Role.ADMIN,
        constants.Role.SUPER_ADMIN,
    }
    is_assigned_agent = (
        requester.role is constants.Role.AGENT
        and ticket.assigned_agent_id == requester.id
    )
    is_owner = requester.role is constants.Role.USER and ticket.creator_user_id == requester.id
    if not (is_manager or is_assigned_agent or is_owner):
        raise AuthorizationError(
            "Customer information is limited to the ticket workspace",
            code="ticket_customer_forbidden",
        )

    customer = operations.get_user(ticket.creator_user_id)
    if customer is None:
        raise TicketNotFoundError("Ticket customer is no longer available")

    return api_models.TicketCustomerSummary(
        user_id=customer.id,
        display_name=f"{customer.first_name} {customer.last_name}".strip(),
        nickname=customer.nickname,
        account_status=customer.user_status,
        email=customer.email if customer.user_status is constants.UserStatus.ACTIVE else None,
        phone=customer.phone if customer.user_status is constants.UserStatus.ACTIVE else None,
        avatar_url=customer.avatar_url,
    )


def _can_manage_ticket_links(ticket: db_models.Ticket, requester: api_models.User) -> bool:
    if requester.role in {
        constants.Role.MANAGER,
        constants.Role.ADMIN,
        constants.Role.SUPER_ADMIN,
    }:
        return True
    return requester.role is constants.Role.AGENT and ticket.assigned_agent_id == requester.id


def _related_ticket_response(
    link: db_models.TicketLink,
    ticket: db_models.Ticket,
) -> api_models.RelatedTicket:
    return api_models.RelatedTicket(
        link_id=link.id,
        ticket_id=ticket.id,
        title=ticket.title,
        status=ticket.status,
        priority=ticket.priority,
        created_at=ticket.created_at,
    )


def list_related_tickets(
    ticket_id: str,
    requester: api_models.User,
) -> list[api_models.RelatedTicket]:
    ticket = operations.get_ticket(ticket_id)
    if ticket is None or not _can_read_ticket(ticket, requester):
        raise TicketNotFoundError()

    result = []
    for link, related_ticket in operations.get_ticket_links(ticket_id):
        if related_ticket.deleted_at is None and _can_read_ticket(related_ticket, requester):
            result.append(_related_ticket_response(link, related_ticket))
    return result


def create_related_ticket(
    ticket_id: str,
    related_ticket_id: str,
    requester: api_models.User,
) -> api_models.RelatedTicket:
    ticket = operations.get_ticket(ticket_id)
    related_ticket = operations.get_ticket(related_ticket_id)
    if ticket is None or related_ticket is None or ticket.deleted_at is not None or related_ticket.deleted_at is not None:
        raise TicketNotFoundError()
    if ticket_id == related_ticket_id:
        raise RelatedTicketConflictError(
            "A ticket cannot be related to itself",
            code="related_ticket_self_link",
        )
    if not _can_manage_ticket_links(ticket, requester) or not _can_read_ticket(related_ticket, requester):
        raise AuthorizationError(
            "You cannot create this related-ticket link",
            code="related_ticket_forbidden",
        )

    left_id, right_id = sorted((ticket_id, related_ticket_id))
    if operations.get_ticket_link(left_id, right_id) is not None:
        raise RelatedTicketConflictError(
            "These tickets are already related",
            code="related_ticket_duplicate",
        )
    now = constants.utc_now()
    link = db_models.TicketLink(
        id=constants.generate_id(),
        ticket_id=left_id,
        related_ticket_id=right_id,
        created_by_user_id=requester.id,
        created_at=now,
    )
    event = api_models.Event(
        id=constants.generate_id(),
        entity_type=constants.EntityType.TICKET,
        entity_id=ticket_id,
        actor_user_id=requester.id,
        event_type=constants.EventType.TICKET_LINKED,
        old_value=None,
        new_value=constants._audit_json({"related_ticket_id": related_ticket_id, "link_id": link.id}),
        metadata=None,
        created_at=now,
    )
    try:
        operations.create_ticket_link(link, event)
    except IntegrityError as exc:
        raise RelatedTicketConflictError(
            "These tickets are already related",
            code="related_ticket_duplicate",
        ) from exc
    return _related_ticket_response(link, related_ticket)


def delete_related_ticket(
    ticket_id: str,
    related_ticket_id: str,
    requester: api_models.User,
) -> bool:
    ticket = operations.get_ticket(ticket_id)
    related_ticket = operations.get_ticket(related_ticket_id)
    if ticket is None or related_ticket is None:
        raise TicketNotFoundError()
    if not _can_manage_ticket_links(ticket, requester):
        raise AuthorizationError(code="related_ticket_forbidden")
    left_id, right_id = sorted((ticket_id, related_ticket_id))
    link = operations.get_ticket_link(left_id, right_id)
    if link is None:
        raise RelatedTicketNotFoundError()
    now = constants.utc_now()
    event = api_models.Event(
        id=constants.generate_id(),
        entity_type=constants.EntityType.TICKET,
        entity_id=ticket_id,
        actor_user_id=requester.id,
        event_type=constants.EventType.TICKET_UNLINKED,
        old_value=constants._audit_json({"related_ticket_id": related_ticket_id, "link_id": link.id}),
        new_value=constants._audit_json({"unlinked": True}),
        metadata=None,
        created_at=now,
    )
    if not operations.delete_ticket_link(link.id, event):
        raise RelatedTicketNotFoundError()
    return True


def get_all_tickets(
        requester: api_models.User,
        limit: int,
        offset: int,
        sort_by: str,
        sort_order: str,
        priority: constants.Priority | None,
        status: constants.Status | None,
        overdue: bool | None = None,
        *,
        assigned_to_me: bool = False,
        department_id: str | None = None,
        assignee_id: str | None = None,
        category: constants.Category | None = None,
        tag: constants.Tag | None = None,
        search: str | None = None,
        ) -> list[api_models.Ticket]:
    if assigned_to_me and requester.role is not constants.Role.AGENT:
        raise AuthorizationError(
            "My Queue is available only to agents",
            code="my_queue_agent_only",
        )
    if assignee_id and requester.role not in {
        constants.Role.MANAGER,
        constants.Role.ADMIN,
        constants.Role.SUPER_ADMIN,
    }:
        raise AuthorizationError(
            "Only managers and administrators can filter by assignee",
            code="assignee_filter_forbidden",
        )

    # Authorization is expressed in SQL before LIMIT/OFFSET. This prevents a
    # page from being shortened by rows the requester cannot see.
    now = constants.utc_now()
    operation_parameters = inspect.signature(operations.get_tickets).parameters
    supports_query_contract = (
        "requester_id" in operation_parameters
        or any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in operation_parameters.values())
    )
    if supports_query_contract:
        tickets = operations.get_tickets(
            limit,
            offset,
            sort_by,
            sort_order,
            priority,
            status,
            overdue,
            now,
            requester_id=requester.id,
            requester_role=requester.role,
            assigned_to_me=assigned_to_me,
            department_id=department_id,
            assignee_id=assignee_id,
            category=category,
            tag=tag,
            search=search,
        )
    else:
        # Compatibility for narrow unit-test doubles and older integrations
        # that still expose the pre-Stage-10 operation signature. Production
        # uses the SQL query contract above.
        legacy_tickets = operations.get_tickets(
            None, 0, sort_by, sort_order, priority, status, overdue, now
        )
        visible_tickets = [
            ticket for ticket in legacy_tickets if _can_read_ticket(ticket, requester)
        ]
        tickets = visible_tickets[offset:offset + limit]
    return [_to_api_ticket(ticket, now=now) for ticket in tickets]


_CUSTOMER_HISTORY_FIELDS = frozenset({
    "status",
    "tags",
    "body",
    "visibility",
    "deleted_at",
    "due_at",
    "priority",
    "is_overdue",
})


def _history_json(raw_value: str | None) -> dict | None:
    if raw_value is None:
        return None
    try:
        value = json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        return {"value": raw_value}
    return value if isinstance(value, dict) else {"value": value}


def _customer_history_value(raw_value: str | None) -> dict | None:
    value = _history_json(raw_value)
    if value is None:
        return None
    return {
        key: field_value
        for key, field_value in value.items()
        if key in _CUSTOMER_HISTORY_FIELDS
    }


def get_ticket_history(
    ticket_id: str,
    requester: api_models.User,
    limit: int,
    offset: int,
) -> list[api_models.TicketHistoryEvent]:
    ticket = operations.get_ticket(ticket_id)
    if ticket is None:
        raise TicketNotFoundError()
    if _can_read_ticket(ticket, requester) is False:
        raise AuthorizationError()

    is_customer = requester.role == constants.Role.USER
    if requester.role in [constants.Role.MANAGER, constants.Role.ADMIN, constants.Role.SUPER_ADMIN]:
        comment_visibilities = None
    elif is_customer:
        comment_visibilities = (constants.Visibility.PUBLIC,)
    else:
        comment_visibilities = (
            constants.Visibility.PUBLIC,
            constants.Visibility.INTERNAL,
        )

    events = operations.get_ticket_history_events(
        ticket_id,
        limit,
        offset,
        comment_visibilities,
    )
    result = []
    for event in events:
        old_value = (
            _customer_history_value(event.old_value)
            if is_customer
            else _history_json(event.old_value)
        )
        new_value = (
            _customer_history_value(event.new_value)
            if is_customer
            else _history_json(event.new_value)
        )
        result.append(api_models.TicketHistoryEvent(
            id=event.id,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            actor_type=event.actor_type,
            actor_user_id=None if is_customer else event.actor_user_id,
            event_type=event.event_type,
            old_value=old_value,
            new_value=new_value or {},
            metadata=None if is_customer else event.metadata_,
            created_at=event.created_at,
        ))
    return result

def update_ticket(updated_info_id: str, updated_info: api_models.TicketUpdate, requester: api_models.User) -> api_models.Ticket:
    ticket = operations.get_ticket(updated_info_id)
    if ticket is None:
        raise TicketNotFoundError()
    if ticket.deleted_at is not None:
        raise TicketDeletedError()

    old_status = ticket.status
    old_assigned_agent_id = ticket.assigned_agent_id

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
    status_was_requested = "status" in requested_fields
    routing_fields = {"department_id", "skill_ids"} & requested_fields

    if requester.role == constants.Role.USER:
        if ticket.creator_user_id != requester.id:
            raise AuthorizationError()
        allowed_fields = {"status", "tags"}
        if requested_fields - allowed_fields:
            raise AuthorizationError("You cannot update these ticket fields", code="ticket_fields_not_allowed")
        if "tags" in requested_fields and ticket.status != constants.Status.NEW:
            raise AuthorizationError("Ticket tags cannot be changed after triage", code="ticket_tags_locked_after_triage")
            
    elif requester.role == constants.Role.AGENT:
        allowed_fields = {"status", "tags"}

        if requested_fields - allowed_fields:
            raise AuthorizationError("You cannot update these ticket fields", code="ticket_fields_not_allowed")

        if ticket.assigned_agent_id != requester.id:
            raise AuthorizationError("The ticket is not assigned to you", code="ticket_not_assigned_to_requester")


    elif requester.role in [
        constants.Role.MANAGER,
        constants.Role.ADMIN,
        constants.Role.SUPER_ADMIN,
    ]:
        allowed_fields = {
            "status",
            "assigned_agent_id",
            "priority",
            "tags",
            "department_id",
            "skill_ids",
            }
        if requested_fields - allowed_fields:
            raise AuthorizationError("You cannot update these ticket fields", code="ticket_fields_not_allowed")
    else:
        raise AuthorizationError()

    if routing_fields:
        if requester.role not in [
            constants.Role.MANAGER,
            constants.Role.ADMIN,
            constants.Role.SUPER_ADMIN,
        ]:
            raise AuthorizationError(
                "Only managers can change ticket routing metadata",
                code="ticket_routing_metadata_forbidden",
            )
        if ticket.status is not constants.Status.NEW or ticket.assigned_agent_id is not None:
            raise TicketStatusConflictError(
                "Ticket routing metadata is locked after assignment",
                code="ticket_routing_metadata_locked",
            )
        if "department_id" in routing_fields and updated_info["department_id"] is None:
            raise InactiveRoutingCatalogError("Ticket department must be active")
        if "skill_ids" in routing_fields and updated_info["skill_ids"] is None:
            raise InactiveRoutingCatalogError("Ticket skill IDs must be a list")
        selected_department_id = updated_info.get("department_id", ticket.department_id)
        selected_skill_ids = updated_info.get("skill_ids", ticket.skill_ids)
        _validate_routing_catalog_selection(selected_department_id, selected_skill_ids)
    
    if 'assigned_agent_id' in updated_info:
        if ticket.status not in constants.TICKET_ASSIGNABLE_STATUSES:
            raise TicketStatusConflictError(
                "Terminal tickets must be reopened before assignment",
            )
        agent = operations.get_user(updated_info['assigned_agent_id'])
        if agent is None:
            raise InvalidAssigneeError("Assignee not found", code="assignee_not_found")
        if agent.role is not constants.Role.AGENT:
            raise InvalidAssigneeError("Assignee must be an agent", code="assignee_must_be_agent")

        # The generic manager PATCH is also the current transfer/reassignment
        # path. Receiving an assignment means waiting in OPEN; starting the
        # work is a separate action owned by the assigned agent.
        if (
            status_was_requested
            and updated_info["status"] != constants.Status.OPEN
        ):
            raise TicketStatusConflictError(
                "Assignment requires open status",
            )
        updated_info["status"] = constants.Status.OPEN
        audit_new_info["status"] = constants.Status.OPEN.value

    if (
        "assigned_agent_id" not in requested_fields
        and status_was_requested
    ):
        if (
            ticket.status == constants.Status.NEW
            and updated_info["status"] == constants.Status.OPEN
        ):
            raise TicketStatusConflictError(
                "Use claim or assignment to open a new ticket",
            )
        if (
            ticket.status == constants.Status.OPEN
            and updated_info["status"] == constants.Status.IN_PROGRESS
        ):
            raise TicketStartWorkConflictError("Use the start-work endpoint for this transition")
        if constants.is_valid_status_transition(ticket.status, updated_info['status']) is False:
            raise TicketStatusConflictError()
        if constants.can_role_transition_ticket(
            requester.role,
            ticket.status,
            updated_info["status"],
        ) is False:
            raise AuthorizationError(
                "Your role cannot perform this ticket transition",
                code="ticket_transition_not_allowed",
            )

    transition_at = constants.utc_now()
    if "status" in updated_info:
        updated_info["due_at"] = constants.calculate_sla_due_at(
            updated_info["status"],
            transition_at,
            updated_info.get("priority", ticket.priority),
        )
        audit_new_info["due_at"] = constants._audit_value(
            updated_info["due_at"]
        )
    elif "priority" in updated_info:
        updated_info["due_at"] = constants.calculate_sla_due_at(
            ticket.status,
            transition_at,
            updated_info["priority"],
        )
        audit_new_info["due_at"] = constants._audit_value(updated_info["due_at"])
        
    
    old_info = {}
    for field in updated_info:
        old_value = getattr(ticket, field, None)

        if field == 'tags':
            old_info[field] = [tag.value for tag in constants.deserialize_tags(old_value)]
        elif field == "skill_ids":
            old_info[field] = list(ticket.skill_ids)
        elif hasattr(old_value, 'value'):
            old_info[field] = old_value.value
        else:
            old_info[field] = constants._audit_value(old_value)

    event = api_models.Event(
        id=constants.generate_id(),
        entity_type=constants.EntityType.TICKET,
        entity_id=ticket.id,
        actor_user_id=requester.id,
        event_type=constants.EventType.TICKET_UPDATED,
        old_value=json.dumps(old_info),
        new_value=json.dumps(audit_new_info),
        metadata=None,
        created_at=transition_at,
    )

    # if status in updates (even with a few fields) -> still status changed
    if 'status' in updated_info.keys():
        event.event_type = constants.EventType.TICKET_STATUS_CHANGED

    ticket = operations.update_ticket(updated_info_id, updated_info, event)

    if ticket is None:
        raise InternalOperationError("Ticket could not be updated", code="ticket_update_failed")


    delete_cached_ticket(ticket.id)

    if (
        routing_fields
        and ticket.department_id is not None
        and ticket.status is constants.Status.NEW
        and ticket.assigned_agent_id is None
    ):
        # Selecting routing metadata makes the durable ticket eligible for the
        # routing queue. Queue failure does not roll back the manager's choice;
        # periodic reconciliation can enqueue it later.
        try:
            enqueue_ticket_routing_job(ticket.id)
        except Exception as exc:
            logger.exception(
                "Ticket routing enqueue failed after routing metadata update",
                extra={"ticket_id": ticket.id},
                exc_info=exc,
            )

    if (
        old_assigned_agent_id is not None
        and old_status in operations.ACTIVE_TICKET_STATUSES
        and ticket.status not in operations.ACTIVE_TICKET_STATUSES
    ):
        dispatch_waiting_tickets_after_capacity_event(
            "ticket_left_active_workload",
            ticket.id,
        )

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
        raise InternalOperationError("Ticket could not be deleted", code="ticket_delete_failed")

    delete_cached_ticket(id)
    if (
        ticket.assigned_agent_id is not None
        and ticket.status in operations.ACTIVE_TICKET_STATUSES
    ):
        dispatch_waiting_tickets_after_capacity_event(
            "active_ticket_deleted",
            ticket.id,
        )
    

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

    released_active_capacity = any(
        ticket.deleted_at is None
        and ticket.assigned_agent_id is not None
        and ticket.status in operations.ACTIVE_TICKET_STATUSES
        for ticket in all_tickets
    )
    deleted_count = operations.delete_all_tickets(events)
    for ticket in all_tickets:
        delete_cached_ticket(ticket.id)
    if released_active_capacity:
        dispatch_waiting_tickets_after_capacity_event(
            "active_tickets_bulk_deleted",
            event.batch_id,
        )
    return deleted_count


def claim_ticket(ticket_id: str, requester: api_models.User) -> api_models.Ticket | None:
    ticket = operations.get_ticket(ticket_id)
    
    if ticket is None:
        raise TicketNotFoundError()
    
    if requester.role != constants.Role.AGENT:
        raise AuthorizationError("Only agents can claim tickets", code="only_agents_can_claim")
    
    if ticket.deleted_at is not None:
        raise TicketDeletedError()
    
    if ticket.assigned_agent_id is not None:
        raise TicketAlreadyAssignedError()
    
    if ticket.status != constants.Status.NEW:
        raise TicketStatusConflictError("Only new tickets can be claimed")
    _require_same_active_department(ticket, requester.id)
    

    transition_at = constants.utc_now()
    new_due_at = constants.calculate_sla_due_at(
        constants.Status.OPEN,
        transition_at,
        ticket.priority,
    )
    event = api_models.Event(
        id=constants.generate_id(),
        entity_type=constants.EntityType.TICKET,
        entity_id=ticket.id,
        actor_user_id=requester.id,
        event_type=constants.EventType.TICKET_CLAIMED,
        old_value=constants._audit_json({
            "status": constants.Status.NEW,
            "assigned_agent_id": None,
            "due_at": getattr(ticket, "due_at", None),
        }),
        new_value=constants._audit_json({
            "status": constants.Status.OPEN,
            "assigned_agent_id": requester.id,
            "due_at": new_due_at,
        }),
        metadata=None,
        created_at=transition_at,
    )
    
    res = operations.claim_ticket(ticket_id, requester.id, event)
    if res is None:
        raise TicketAlreadyAssignedError()

    delete_cached_ticket(ticket_id)
    s_notifications.emit(
        requester.id,
        "ticket_assigned",
        f"Ticket #{ticket_id[:8]} was assigned to you.",
        ticket_id=ticket_id,
        idempotency_key=f"ticket-assigned:{ticket_id}:{requester.id}",
    )
    
    return _to_api_ticket(res)


def assign_ticket(ticket_id: str, agent_id: str, requester: api_models.User) -> api_models.Ticket | None:
    ticket = operations.get_ticket(ticket_id)


    if ticket is None:
        raise TicketNotFoundError()
    if ticket.deleted_at is not None:
        raise TicketDeletedError()
    if ticket.status not in constants.TICKET_ASSIGNABLE_STATUSES:
        raise TicketStatusConflictError(
            "Terminal tickets must be reopened before assignment",
        )
    is_reassign = False
    if ticket.assigned_agent_id is not None:
        is_reassign = True
    
    agent = operations.get_user(agent_id)
    if agent is None:
        raise InvalidAssigneeError("Assignee not found", code="assignee_not_found")
    
    if requester.role not in [
        constants.Role.MANAGER,
        constants.Role.ADMIN,
        constants.Role.SUPER_ADMIN,
    ]:
        raise AuthorizationError()

    if agent.role != constants.Role.AGENT:
        raise InvalidAssigneeError("Assignee must be an agent", code="assignee_must_be_agent")
    _require_same_active_department(ticket, agent.id)

    transition_at = constants.utc_now()
    new_due_at = constants.calculate_sla_due_at(
        constants.Status.OPEN,
        transition_at,
        ticket.priority,
    )
    event = api_models.Event(
       id=constants.generate_id(),
       entity_type=constants.EntityType.TICKET,
       entity_id=ticket.id,
       actor_user_id=requester.id,
       event_type=constants.EventType.TICKET_ASSIGNED,
       old_value=constants._audit_json({
           "status": ticket.status,
           "assigned_agent_id": ticket.assigned_agent_id,
           "due_at": getattr(ticket, "due_at", None),
       }),
       new_value=constants._audit_json({
           "status": constants.Status.OPEN,
           "assigned_agent_id": agent_id,
           "due_at": new_due_at,
       }),
       metadata=None,
       created_at=transition_at,
    )   

    if is_reassign:
        event.event_type = constants.EventType.TICKET_REASSIGNED

    res = operations.assign_ticket(ticket.id, agent.id, event)
    if res is None:
        raise InternalOperationError("Ticket could not be assigned", code="ticket_assignment_failed")

    delete_cached_ticket(ticket_id)
    s_notifications.emit(
        agent.id,
        "ticket_assigned",
        f"Ticket #{ticket.id[:8]} was assigned to you.",
        ticket_id=ticket.id,
        idempotency_key=f"ticket-assigned:{ticket.id}:{agent.id}:{transition_at.isoformat()}",
    )

    return _to_api_ticket(res)


def start_ticket_work(
    ticket_id: str,
    requester: api_models.User,
) -> api_models.Ticket:
    if requester.role != constants.Role.AGENT:
        raise AuthorizationError("Only the assigned agent can start work", code="only_assigned_agent_can_start_work")

    result = operations.start_ticket_work(ticket_id, requester.id)
    match result.outcome:
        case constants.StartWorkOutcome.STARTED:
            if result.ticket is None:
                raise InternalOperationError("Ticket state could not be loaded", code="start_work_missing_ticket")
        case constants.StartWorkOutcome.TICKET_NOT_FOUND:
            raise TicketNotFoundError()
        case constants.StartWorkOutcome.TICKET_DELETED:
            raise TicketDeletedError()
        case constants.StartWorkOutcome.ASSIGNED_TO_ANOTHER_AGENT:
            raise AuthorizationError("The ticket is assigned to another agent", code="ticket_assigned_to_another_agent")
        case constants.StartWorkOutcome.TICKET_UNASSIGNED:
            raise TicketStartWorkConflictError("The ticket is not assigned")
        case constants.StartWorkOutcome.TICKET_ALREADY_STARTED:
            raise TicketStartWorkConflictError("Work has already started")
        case constants.StartWorkOutcome.TICKET_NOT_OPEN:
            raise TicketStartWorkConflictError("Only open tickets can be started")
        case _:
            raise InternalOperationError("Ticket work could not be started", code="unknown_start_work_outcome")

    delete_cached_ticket(ticket_id)
    return _to_api_ticket(result.ticket)
