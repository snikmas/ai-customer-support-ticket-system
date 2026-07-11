# functions that the worker runs
# shouldn't touch the queue
from src.db import get_ticket
from src.exceptions import TicketNotFoundError

def inspect_ticket(ticket_id: str) -> dict:
    # Run a small, deterministic background check without AI
    ticket = get_ticket(ticket_id)
    if ticket is None:
        raise TicketNotFoundError()

    return {
        "ticket_id": ticket_id,
        "status": ticket.status.value,
        "priority": ticket.priority.value,
        "deleted": ticket.deleted_at is not None,
    }
