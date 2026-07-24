from src import constants
from src import models as api_models
from src.analyzers import AnalysisInputSnapshot, configured_analyzer_metadata
from src.cache import consume_analysis_creation_allowance
from src.db import models as db_models
from src.db import operations
from src.exceptions import (
    AnalysisEnqueueUnavailableError,
    AnalysisResultNotFoundError,
    AuthorizationError,
    TicketDeletedError,
    TicketNotFoundError,
)


HUMAN_MANAGER_ROLES = {
    constants.Role.MANAGER,
    constants.Role.ADMIN,
    constants.Role.SUPER_ADMIN,
}


def _to_api_result(result: db_models.AnalysisResult) -> api_models.AnalysisResult:
    return api_models.AnalysisResult.model_validate(result)


def _authorize_creation(ticket: db_models.Ticket, requester: api_models.User) -> None:
    if requester.role in HUMAN_MANAGER_ROLES:
        return
    if (
        requester.role is constants.Role.AGENT
        and ticket.assigned_agent_id == requester.id
    ):
        return
    raise AuthorizationError(
        "You cannot request analysis for this ticket",
        code="ticket_analysis_forbidden",
    )


MAX_PUBLIC_COMMENT_CHARACTERS = 8_000


def _bounded_public_comment_bodies(
    newest_first_comments: list[db_models.Comment],
) -> tuple[str, ...]:
    """Keep newest content within the budget, then restore reading order."""
    remaining = MAX_PUBLIC_COMMENT_CHARACTERS
    newest_first_bodies: list[str] = []
    for comment in newest_first_comments:
        if remaining == 0:
            break
        body = comment.body[:remaining]
        if body:
            newest_first_bodies.append(body)
            remaining -= len(body)
    return tuple(reversed(newest_first_bodies))


def _snapshot_for_ticket(
    ticket: db_models.Ticket,
    public_comments: list[db_models.Comment],
) -> AnalysisInputSnapshot:
    tags = (
        constants.deserialize_tags(ticket.tags)
        if ticket.tags is None or isinstance(ticket.tags, str)
        else ticket.tags
    )
    return AnalysisInputSnapshot(
        title=ticket.title,
        description=ticket.description,
        category=ticket.category,
        tags=tuple(tags),
        priority=ticket.priority,
        status=ticket.status,
        public_comments=_bounded_public_comment_bodies(public_comments),
    )


def request_analysis(
    ticket_id: str,
    requester: api_models.User,
) -> api_models.AnalysisResult:
    now = constants.utc_now()

    def authorize(ticket: db_models.Ticket) -> None:
        if ticket.deleted_at is not None:
            raise TicketDeletedError()
        _authorize_creation(ticket, requester)

    def build_result(
        ticket: db_models.Ticket,
        public_comments: list[db_models.Comment],
    ) -> db_models.AnalysisResult:
        analyzer_metadata = configured_analyzer_metadata()
        return db_models.AnalysisResult(
            id=constants.generate_id(),
            input_snapshot=_snapshot_for_ticket(
                ticket,
                public_comments,
            ).model_dump_json(),
            summary=None,
            error_code=None,
            error_message=None,
            ticket_id=ticket.id,
            job_id=None,
            provider=analyzer_metadata.provider,
            model=analyzer_metadata.model,
            prompt_version=analyzer_metadata.prompt_version,
            input_tokens=None,
            output_tokens=None,
            requester_id=requester.id,
            attempt_count=0,
            created_at=now,
            started_at=None,
            completed_at=None,
            updated_at=now,
            status=constants.AnalysisStatus.PENDING,
        )

    reservation = operations.reserve_analysis_result(
        ticket_id,
        authorize_ticket=authorize,
        consume_allowance=lambda: consume_analysis_creation_allowance(requester.id),
        build_result=build_result,
    )
    if reservation is None:
        raise TicketNotFoundError()
    if not reservation.created:
        return _to_api_result(reservation.result)

    from src.jobs.service import enqueue_analysis_result_job

    try:
        job = enqueue_analysis_result_job(reservation.result.id)
        attached = operations.attach_analysis_job(
            reservation.result.id,
            job.id,
            constants.utc_now(),
        )
        if attached is None:
            raise RuntimeError("analysis job link could not be persisted")
        return _to_api_result(attached)
    except Exception as exc:
        operations.fail_analysis_result(
            reservation.result.id,
            expected_statuses=(
                constants.AnalysisStatus.PENDING,
                constants.AnalysisStatus.RUNNING,
            ),
            error_code="enqueue_failed",
            error_message="Analysis could not be queued",
            now=constants.utc_now(),
        )
        constants.logger.warning(
            "Analysis enqueue failed",
            extra={"analysis_result_id": reservation.result.id},
        )
        raise AnalysisEnqueueUnavailableError() from exc


def get_analysis_result(
    analysis_result_id: str,
    requester: api_models.User,
) -> api_models.AnalysisResult:
    result = operations.get_analysis_result(analysis_result_id)
    if result is None:
        raise AnalysisResultNotFoundError()

    ticket = operations.get_ticket(result.ticket_id) if result.ticket_id is not None else None
    if ticket is None or ticket.deleted_at is not None:
        if requester.role not in HUMAN_MANAGER_ROLES:
            raise AuthorizationError(
                "Only managers can view preserved analysis results",
                code="preserved_analysis_forbidden",
            )
    elif not (
        requester.role in HUMAN_MANAGER_ROLES
        or (
            requester.role is constants.Role.AGENT
            and (
                ticket.assigned_agent_id == requester.id
                or result.requester_id == requester.id
            )
        )
    ):
        raise AuthorizationError(
            "You cannot view this analysis result",
            code="analysis_result_forbidden",
        )

    return _to_api_result(result)


def get_ticket_analysis_results(
    ticket_id: str,
    requester: api_models.User,
    *,
    limit: int,
    offset: int,
) -> list[api_models.AnalysisResult]:
    ticket = operations.get_ticket(ticket_id)
    if ticket is None:
        raise TicketNotFoundError()

    if ticket.deleted_at is not None:
        if requester.role not in HUMAN_MANAGER_ROLES:
            raise AuthorizationError(
                "Only managers can view preserved analysis history",
                code="preserved_analysis_forbidden",
            )
    elif not (
        requester.role in HUMAN_MANAGER_ROLES
        or (
            requester.role is constants.Role.AGENT
            and ticket.assigned_agent_id == requester.id
        )
    ):
        raise AuthorizationError(
            "You cannot view this ticket's analysis history",
            code="analysis_history_forbidden",
        )

    return [
        _to_api_result(result)
        for result in operations.get_analysis_results_by_ticket(
            ticket_id,
            limit=limit,
            offset=offset,
        )
    ]
