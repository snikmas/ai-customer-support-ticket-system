from datetime import datetime
from .permissions import check_for_access
from src import constants
from src.models import models as api_models
from src.db import models as db_models
from src.db import operations

def create_ticket(ticket_data: api_models.TicketCreate, requester: api_models.User) -> db_models.Ticket:
    now = datetime.now()

    if (check_for_access(requester.role, constants.Role.USER)) is False:
        raise PermissionError

    ticket = db_models.Ticket(
        id=constants.generate_id(),
        title=ticket_data.title,
        description=ticket_data.description,
        category=ticket_data.category,
        tags=ticket_data.tags,
        assigned_agent_id=None,
        creator_user_id=requester.id,
        status=ticket_data.status,
        priority=ticket_data.priority,
        updated_at=now,
        created_at=now
    )
    
    operations.create_ticket(ticket)
    return ticket

def get_ticket(id: str, requester: api_models.User) -> db_models.Ticket: #im not sure is it a db ticket or api model
    if check_for_access(requester.role, constants.Role.USER) is False:
        raise PermissionError
    
    ticket = operations.get_ticket(id)
    if ticket is None:
        raise ValueError("ticket_not_found")
    
    return ticket

def get_all_tickets(requester: api_models.User) -> list[db_models.Ticket]:
    if check_for_access(requester.role, constants.Role.MANAGER) is False:
        raise PermissionError

    return operations.get_tickets()

def update_ticket(updated_info_id: str, updated_info: api_models.TicketUpdate, requester: api_models.User) -> db_models.Ticket:
    ticket = operations.get_ticket(updated_info_id)
    if ticket is None:
        raise ValueError("ticket_not_found")

    updated_info = updated_info.model_dump(exclude_unset=True)
    if not updated_info:
        raise ValueError("empty_update")

    if check_for_access(requester, constants.Role.MANAGER) is False: #im not sure admin/manager? agent is not suitable
        raise PermissionError
    
    if 'status' in updated_info and constants.is_valid_status_transition(ticket.status, updated_info['status']) is False:
        raise ValueError("Invalid Status Transition")


    res = operations.update_ticket(updated_info_id, updated_info)
    if res is None:
        raise ValueError("Some error during updating, the operation canceled")
    return res

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
    
