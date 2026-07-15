# functions that the worker runs
# shouldn't touch the queue
from src.db import get_ticket, create_analysis_result
from src.exceptions import TicketNotFoundError
from src.constants import logger

def inspect_ticket(ticket_id: str) -> dict:
    # Run a small, deterministic background check without AI
    logger.info("Ticket inspection started", extra={"ticket_id": ticket_id})
    ticket = get_ticket(ticket_id)
    if ticket is None:
        logger.warning(
            "Ticket inspection failed because the ticket was not found",
            extra={"ticket_id": ticket_id},
        )
        raise TicketNotFoundError()

    result = {
        "ticket_id": ticket_id,
        "status": ticket.status.value,
        "priority": ticket.priority.value,
        "deleted": ticket.deleted_at is not None,
    }
    res = create_analysis_result(result)
    if res is False: raise ValueError
    logger.info("Ticket inspection completed", extra={"ticket_id": ticket_id})
    return result
