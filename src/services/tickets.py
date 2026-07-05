from datetime import datetime
from .permissions import check_for_access
from src import constants

from src.models import models as api_models
from src.db import models as db_models
from src.db import operations

def create_ticket(ticket_data: api_models.TicketCreate, requester: api_models.User) -> api_models.Ticket:
    now = datetime.now()

    if (check_for_access(requester.role, constants.Role.USER)) is False:
        raise PermissionError
    
    ticket = db_models.Ticket(
        id=constants.generate_id(),
        title=ticket_data.title,
        description=ticket_data.description,
        category=ticket_data.category,
        tags=constants.serialize_tags(ticket_data.tags),
        assigned_agent_id=None,
        creator_user_id=requester.id,
        status=ticket_data.status,
        priority=ticket_data.priority,
        updated_at=now,
        created_at=now,
        deleted_at=None
    )
    
    ticket = api_models.Ticket(operations.create_ticket(ticket))
    return ticket


def get_ticket(id: str, requester: api_models.User) -> api_models.Ticket: #im not sure is it a db ticket or api model
    if check_for_access(requester.role, constants.Role.USER) is False:
        raise PermissionError
    
    ticket = operations.get_ticket(id)
    if ticket is None or (ticket.deleted_at is not None and check_for_access(requester.role, constants.Role.ADMIN)):
        raise ValueError("ticket_not_found")

    if ticket.tags:
        ticket.tags = constants.deserialize_tags(ticket.tags)
    
    ticket.tags = constants.deserialize_tags(ticket.tags)

    return api_models.Ticket(ticket)


def get_all_tickets(requester: api_models.User) -> list[api_models.Ticket]:
    
    tickets = operations.get_tickets()

    
    for ticket in tickets:
        if ticket.tags: ticket.tags = constants.deserialize_tags(ticket.tags)
    
    if check_for_access(requester.role, constants.Role.ADMIN):
        return tickets
    
    tickets = [api_models.Ticket(ticket) for ticket in tickets if ticket.deleted_at is None and ticket.creator_user_id == requester.id]

    return tickets

def update_ticket(updated_info_id: str, updated_info: api_models.TicketUpdate, requester: api_models.User) -> api_models.Ticket:
    ticket = operations.get_ticket(updated_info_id)
    if ticket is None or (ticket.deleted_at is not None and check_for_access(requester.role, constants.Role.MANAGER)):
        raise ValueError("ticket_not_found")

    # ================= STANDARTIZATION PROCESS ========================
    updated_info = updated_info.model_dump(exclude_unset=True)

    if not updated_info:
        raise ValueError("empty_update")

    if 'tags' in updated_info and updated_info['tags'] is not None:
        updated_info['tags'] = constants.serialize_tags(updated_info['tags'])
        
    # =================================================================
    # ================= ACCESS PROCCESS ===============================
    
    requested_fields = set(updated_info.keys())

    if requester.role == constants.Role.USER:
        if 'status' not in requested_fields or len(requested_fields) > 1 or updated_info['status'] not in [constants.Status.OPEN, constants.Status.CLOSED]:
            return None
            
    elif requester.role == constants.Role.AGENT:
        allowed_fields = {"status", "category"}

        if requested_fields - allowed_fields:
            return None

        if ticket.assigned_agent_id != requester.id:
            return None


    elif check_for_access(requester.role, constants.Role.MANAGER):
        allowed_fields = {
            "status",
            "assigned_agent_id",
            "priority",
            "category",
            }
        if requested_fields - allowed_fields: return None
    else:
        return None
    
    if 'assigned_agent_id' in updated_info:
        agent = operations.get_user(updated_info['assigned_agent_id'])
        if agent is None:
            return None


    if "status" in requested_fields:
        if constants.is_valid_status_transition(ticket.status, updated_info['status']) is False:
            return None

    ticket = operations.update_ticket(updated_info_id, updated_info)
    ticket['tags'] = constants.deserialize_tags(ticket['tags'])
    if ticket is None:
        raise ValueError("Some error during updating, the operation canceled")
    return api_models.Ticket(ticket)

def delete_ticket(id: str, requester: api_models.User) -> None:
    ticket = operations.get_ticket(id)

    if ticket is None:
        raise ValueError("ticket_not_found")

    if ticket.creator_user_id != requester.id:
        if check_for_access(requester.role, constants.Role.ADMIN) is False: 
            raise PermissionError
    
    if operations.delete_ticket(id) is False:
        raise ValueError("Some error during deleting, the operation cancelled")

def delete_all_tickets(requester: api_models.User) -> int:
    user = operations.get_user(requester.id)
    if user is None:
        raise ValueError("user_not_found")
    
    if check_for_access(user.role, constants.Role.SUPER_ADMIN) is False:
        raise PermissionError
    
    deleted_tickets = operations.delete_all_tickets()
    
    return deleted_tickets


def claim_ticket(ticket_id: str, requester: api_models.User) -> api_models.Ticket | None:
    ticket = operations.get_ticket(ticket_id)
    
    if ticket is None:
        raise ValueError("ticket_not_found")
    
    if check_for_access(requester.role, constants.Role.AGENT) is False:
        raise PermissionError("only_agents_can_claim")
    
    if ticket.deleted_at is not None:
        raise ValueError("ticket_deleted")
    
    if ticket.assigned_agent_id is not None:
        raise ValueError("ticket_already_assigned")
    
    if ticket.status != constants.Status.NEW:
        raise ValueError("ticket_not_new")
    
    
    res = operations.claim_ticket(ticket_id, requester.id)
    if res is None:
        raise ValueError("ticket_not_found")
    
    return res


def assign_ticket(ticket_id: str, agent_id: str, requester: api_models.User) -> api_models.Ticket | None:
    ticket = operations.get_ticket(ticket_id)

    if ticket is None:
        raise ValueError("ticket_not_found")
    
    agent = operations.get_user(agent_id)
    if agent is None:
        raise ValueError("ticket_not_found")
    
    if check_for_access(requester.role, constants.Role.MANAGER) is False: return None

    if agent.role not in [constants.Role.AGENT, constants.Role.MANAGER]: return None

    if requester.role == agent.role: return None

    res = operations.assign_ticket(ticket.id, agent.id)
    
    return res