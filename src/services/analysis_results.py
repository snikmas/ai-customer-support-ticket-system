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
from src.cache import check_ticket as check_cached_ticket, cache_ticket, delete_ticket as delete_cached_ticket
from src.jobs import start_ticket_inspection_job, get_job as jobs_get_job
import json


def get_all_analysis_results(ticket_id: str, requester: api_models.User) -> list[api_models.AnalysisResult] | None:
    if check_for_access(requester.role, constants.Role.AGENT) is False: raise AuthorizationError()

    ticket = operations.get_ticket(ticket_id)
    if ticket is None: raise TicketNotFoundError()

    if requester.role == constants.Role.AGENT:
        if ticket.assigned_agent_id != requester.id: raise AuthorizationError()

    res = operations.get_analysis_results_by_ticket(ticket_id)
    return res

    

    


        
