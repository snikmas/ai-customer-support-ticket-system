# functions that the worker runs
# shouldn't touch the queue
from redis import RedisError
from rq import get_current_job
from sqlalchemy.exc import OperationalError

from src.cache import delete_ticket as delete_cached_ticket
from src.db import (
    get_ticket,
    try_route_ticket,
)
from src.exceptions import TicketNotFoundError
from src.constants import TicketRoutingOutcome, logger

TEMPORARY_ROUTING_ERRORS = (
    ConnectionError,
    OperationalError,
    RedisError,
    TimeoutError,
)

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
    logger.info("Ticket inspection completed", extra={"ticket_id": ticket_id})
    return result


def route_ticket(ticket_id: str) -> dict:
    """Run the database-owned routing decision once.

    Normal domain outcomes are returned instead of raised, so RQ retries only
    unexpected technical failures from the database/task infrastructure.
    """
    logger.info("Ticket routing started", extra={"ticket_id": ticket_id})
    try:
        result = try_route_ticket(ticket_id)
    except TEMPORARY_ROUTING_ERRORS:
        # Leave the RQ retry budget intact for transient connection, timeout,
        # or database-operational failures.
        logger.warning(
            "Ticket routing hit a temporary technical failure",
            extra={"ticket_id": ticket_id},
            exc_info=True,
        )
        raise
    except Exception:
        # RQ's Retry object normally retries every exception. Clear the retry
        # budget for programming/data-integrity failures that waiting will not
        # repair, while still letting RQ mark the job as failed.
        current_job = get_current_job()
        if current_job is not None:
            current_job.retries_left = 0
            current_job.save()
        logger.exception(
            "Ticket routing hit a non-retryable technical failure",
            extra={"ticket_id": ticket_id},
        )
        raise

    if result.outcome is TicketRoutingOutcome.ASSIGNED:
        # Cache deletion is fail-open in this project. The database remains the
        # source of truth even if Redis is temporarily unavailable.
        delete_cached_ticket(ticket_id)

    logger.info(
        "Ticket routing completed",
        extra={
            "ticket_id": ticket_id,
            "routing_outcome": result.outcome.value,
            "assigned_agent_id": result.assigned_agent_id,
        },
    )
    return {
        "outcome": result.outcome.value,
        "ticket_id": result.ticket_id,
        "assigned_agent_id": result.assigned_agent_id,
    }
