# functions that the worker runs
# shouldn't touch the queue
from redis import RedisError
from rq import get_current_job
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from src.cache import delete_ticket as delete_cached_ticket
from src.db import (
    complete_analysis_result,
    fail_analysis_result,
    get_analysis_result,
    get_ticket,
    record_overdue_ticket_events,
    return_analysis_to_pending,
    start_analysis_attempt,
    try_route_ticket,
)
from src.constants import AnalysisStatus, TicketRoutingOutcome, logger
from src.constants import utc_now
from src.analyzers import (
    AnalysisInputSnapshot,
    PermanentAnalysisError,
    RetryableAnalysisError,
    build_fake_analyzer,
)

TEMPORARY_ROUTING_ERRORS = (
    ConnectionError,
    OperationalError,
    RedisError,
    TimeoutError,
)

def _disable_current_job_retries() -> None:
    current_job = get_current_job()
    if current_job is not None:
        current_job.retries_left = 0
        current_job.save()


def _fail_analysis_permanently(
    analysis_result_id: str,
    *,
    error_code: str,
    error_message: str,
) -> None:
    fail_analysis_result(
        analysis_result_id,
        expected_statuses=(AnalysisStatus.RUNNING,),
        error_code=error_code,
        error_message=error_message,
        now=utc_now(),
    )
    _disable_current_job_retries()


def analyze_analysis_result(analysis_result_id: str) -> dict:
    """Run one attempt and persist every lifecycle transition on one SQL row."""
    logger.info(
        "Analysis attempt started",
        extra={"analysis_result_id": analysis_result_id},
    )
    running = start_analysis_attempt(analysis_result_id, utc_now())
    if running is None:
        existing = get_analysis_result(analysis_result_id)
        if existing is not None and existing.status in {
            AnalysisStatus.COMPLETED,
            AnalysisStatus.FAILED,
        }:
            return {
                "analysis_result_id": existing.id,
                "status": existing.status.value,
            }
        _disable_current_job_retries()
        raise PermanentAnalysisError("analysis result is not runnable")

    ticket = get_ticket(running.ticket_id) if running.ticket_id is not None else None
    if ticket is None or ticket.deleted_at is not None:
        _fail_analysis_permanently(
            analysis_result_id,
            error_code="ticket_deleted",
            error_message="Ticket was deleted before analysis",
        )
        logger.warning(
            "Analysis permanently failed because its ticket was deleted",
            extra={"analysis_result_id": analysis_result_id},
        )
        raise PermanentAnalysisError("ticket deleted")

    try:
        snapshot = AnalysisInputSnapshot.model_validate_json(running.input_snapshot)
        output = build_fake_analyzer().analyze(snapshot)
    except RetryableAnalysisError:
        if running.attempt_count < 3:
            return_analysis_to_pending(analysis_result_id, utc_now())
            logger.warning(
                "Analysis attempt will be retried",
                extra={
                    "analysis_result_id": analysis_result_id,
                    "attempt_count": running.attempt_count,
                },
            )
            raise

        _fail_analysis_permanently(
            analysis_result_id,
            error_code="analysis_retry_exhausted",
            error_message="Analysis failed after three attempts",
        )
        logger.warning(
            "Analysis retry budget exhausted",
            extra={"analysis_result_id": analysis_result_id},
        )
        raise
    except ValidationError:
        _fail_analysis_permanently(
            analysis_result_id,
            error_code="invalid_analysis_snapshot",
            error_message="Stored analysis input is invalid",
        )
        logger.warning(
            "Analysis snapshot validation failed",
            extra={"analysis_result_id": analysis_result_id},
        )
        raise PermanentAnalysisError("invalid analysis snapshot") from None
    except PermanentAnalysisError:
        _fail_analysis_permanently(
            analysis_result_id,
            error_code="analysis_permanent_failure",
            error_message="Analysis could not process this ticket",
        )
        logger.warning(
            "Analysis permanently rejected its input",
            extra={"analysis_result_id": analysis_result_id},
        )
        raise
    except Exception:
        if running.attempt_count < 3:
            return_analysis_to_pending(analysis_result_id, utc_now())
            raise RetryableAnalysisError("temporary analyzer failure") from None
        _fail_analysis_permanently(
            analysis_result_id,
            error_code="analysis_retry_exhausted",
            error_message="Analysis failed after three attempts",
        )
        raise RetryableAnalysisError("analysis retry budget exhausted") from None

    completed = complete_analysis_result(
        analysis_result_id,
        output.summary,
        utc_now(),
    )
    if completed is None:
        raise PermanentAnalysisError("analysis completion transition failed")

    logger.info(
        "Analysis completed",
        extra={"analysis_result_id": analysis_result_id},
    )
    return {
        "analysis_result_id": analysis_result_id,
        "status": AnalysisStatus.COMPLETED.value,
    }


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


def scan_overdue_tickets(batch_size: int) -> dict:
    """Record one bounded page of idempotent SLA-overdue events."""
    ticket_ids = record_overdue_ticket_events(batch_size, utc_now())
    result = {"scanned": len(ticket_ids), "ticket_ids": ticket_ids}
    logger.info("Overdue ticket scan completed", extra=result)
    return result
