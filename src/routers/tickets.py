from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from src import models, db, constants
from src.services import attachments as s_attachments
from src.services import users as s_users, tickets as s_tickets, comments as s_comments
from src.services import analysis_results as s_analysis_results
from src.dependencies.auth import get_current_user
from typing import Literal
import inspect

router = APIRouter(
    prefix="/tickets",
    tags=["tickets"]
)

# This router intentionally uses normal `def` handlers because SQLAlchemy,
# Redis, and RQ are synchronous in the current stack. A later end-to-end async
# migration would require AsyncSession + an async DB driver and async Redis/HTTP
# clients; only then should these handlers become `async def` and use `await`.

@router.get("/", status_code=200)
def get_tickets(requester = Depends(get_current_user),
                    limit: int = Query(constants.DEFAULT_PAGE_LIMIT, 
                                         ge=1,
                                         le=constants.MAX_PAGE_LIMIT),
                    offset: int = Query(0, ge=0),
                    sort_by: Literal['created_at', 'updated_at', 'status', 'priority'] = constants.DEFAULT_SORT_BY,
                    sort_order: Literal['asc', 'desc'] = constants.DEFAULT_SORT_ORDER,
                    priority: constants.Priority | None = None,
                    status: constants.Status | None = None,
                    overdue: bool | None = None,
                    search: str | None = Query(None, max_length=200),
                    assigned_to_me: bool = False,
                    department_id: str | None = None,
                    assignee_id: str | None = None,
                    category: constants.Category | None = None,
                    tag: constants.Tag | None = None,
                    ):
    service_parameters = inspect.signature(s_tickets.get_all_tickets).parameters
    supports_query_contract = (
        "assigned_to_me" in service_parameters
        or any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in service_parameters.values())
    )
    if supports_query_contract:
        data = s_tickets.get_all_tickets(
            requester,
            limit,
            offset,
            sort_by,
            sort_order,
            priority,
            status,
            overdue,
            assigned_to_me=assigned_to_me,
            department_id=department_id,
            assignee_id=assignee_id,
            category=category,
            tag=tag,
            search=search,
        )
    else:
        data = s_tickets.get_all_tickets(
            requester,
            limit,
            offset,
            sort_by,
            sort_order,
            priority,
            status,
            overdue,
        )
    return {"data": data}


@router.get("/{id}", status_code=200)
def get_ticket(id: str, requester = Depends(get_current_user)):
    data = s_tickets.get_ticket(id, requester)
    return {"data": data}


@router.get("/{ticket_id}/customer", status_code=200)
def get_ticket_customer(
    ticket_id: str,
    requester: models.User = Depends(get_current_user),
):
    return {"data": s_tickets.get_ticket_customer_summary(ticket_id, requester)}


@router.post("/", status_code=201)
def create_ticket(cur_ticket: models.TicketCreate, requester = Depends(get_current_user)):
    
    ticket = s_tickets.create_ticket(cur_ticket, requester)
    
    return {"data": ticket}


@router.patch("/{ticket_id}", status_code=200)
def update_ticket(ticket_id: str, new_info: models.TicketUpdate, requester = Depends(get_current_user)):
    
    data = s_tickets.update_ticket(ticket_id, new_info, requester)
    return {'data': data}

    
@router.delete("/{id}", status_code=200)
def delete_ticket(id: str, requester = Depends(get_current_user)):

    data = s_tickets.delete_ticket(id, requester)
    return {'data': data}


@router.delete("/", status_code=200)
def delete_all_tickets(requester = Depends(get_current_user)):

    data = s_tickets.delete_all_tickets(requester)
    return {'data': data}

@router.post("/{ticket_id}/claim", status_code=200)
def claim_ticket(ticket_id: str, requester: models.User = Depends(get_current_user)):
    data = s_tickets.claim_ticket(ticket_id, requester)
    return {'data': data}

@router.post("/{ticket_id}/assign", status_code=200)
def assign_ticket(ticket_id: str, assign_ticket_req: models.AssignTicketRequest, requester: models.User = Depends(get_current_user)):
    data = s_tickets.assign_ticket(ticket_id, assign_ticket_req.agent_id, requester)
    return {'data': data}


@router.post("/{ticket_id}/start-work", status_code=200)
def start_ticket_work(
    ticket_id: str,
    requester: models.User = Depends(get_current_user),
):
    return {"data": s_tickets.start_ticket_work(ticket_id, requester)}


@router.get("/{ticket_id}/history", status_code=200)
def get_ticket_history(
    ticket_id: str,
    requester: models.User = Depends(get_current_user),
    limit: int = Query(constants.DEFAULT_PAGE_LIMIT, ge=1, le=constants.MAX_PAGE_LIMIT),
    offset: int = Query(0, ge=0),
):
    return {
        "data": s_tickets.get_ticket_history(
            ticket_id,
            requester,
            limit,
            offset,
        )
    }


@router.get("/{ticket_id}/related", status_code=200)
def list_related_tickets(
    ticket_id: str,
    requester: models.User = Depends(get_current_user),
):
    return {"data": s_tickets.list_related_tickets(ticket_id, requester)}


@router.post("/{ticket_id}/related", status_code=201)
def create_related_ticket(
    ticket_id: str,
    request: models.RelatedTicketCreate,
    requester: models.User = Depends(get_current_user),
):
    return {
        "data": s_tickets.create_related_ticket(
            ticket_id,
            request.related_ticket_id,
            requester,
        )
    }


@router.delete("/{ticket_id}/related/{related_ticket_id}", status_code=204)
def delete_related_ticket(
    ticket_id: str,
    related_ticket_id: str,
    requester: models.User = Depends(get_current_user),
):
    s_tickets.delete_related_ticket(ticket_id, related_ticket_id, requester)


@router.get("/{ticket_id}/comments", status_code=200)
def get_ticket_comments(
            ticket_id: str, 
            requester: models.User = Depends(get_current_user),
            limit: int = Query(constants.DEFAULT_PAGE_LIMIT, 
                                         ge=1,
                                         le=constants.MAX_PAGE_LIMIT),
            offset: int = Query(0, ge=0),
            sort_by: Literal['created_at', 'updated_at'] = 'created_at',
            sort_order: Literal['asc', 'desc'] = constants.DEFAULT_SORT_ORDER,
            ):
    data = s_comments.get_all_comments(ticket_id, requester, limit, offset, sort_by, sort_order)
    return {"data": data}

@router.post("/{ticket_id}/comments", status_code=201)
def create_ticket_comment(ticket_id: str, comment: models.CommentCreate, requester: models.User = Depends(get_current_user)):
    data = s_comments.create_ticket_comment(ticket_id, comment, requester)
    return {"data": data}

@router.get("/{ticket_id}/comments/{comment_id}", status_code=200)
def get_ticket_comment(ticket_id: str, comment_id: str, requester: models.User = Depends(get_current_user)):
    data = s_comments.get_comment(ticket_id, comment_id, requester)
    return {"data": data}

@router.patch("/{ticket_id}/comments/{comment_id}", status_code=200)
def update_ticket_comment(ticket_id: str, comment_id: str, new_info: models.CommentUpdate, requester: models.User = Depends(get_current_user)):
    data = s_comments.update_comment(ticket_id, comment_id, new_info, requester)
    return {"data": data}

@router.delete("/{ticket_id}/comments/{comment_id}", status_code=200)
def delete_ticket_comment(ticket_id: str, comment_id: str, requester: models.User = Depends(get_current_user)):
    data = s_comments.delete_comment(ticket_id, comment_id, requester)
    return {"data": data}


@router.get("/{ticket_id}/comments/{comment_id}/attachments", status_code=200)
def list_comment_attachments(
    ticket_id: str,
    comment_id: str,
    requester: models.User = Depends(get_current_user),
):
    return {"data": s_attachments.list_attachments(ticket_id, comment_id, requester)}


@router.post("/{ticket_id}/comments/{comment_id}/attachments", status_code=201)
async def upload_comment_attachment(
    ticket_id: str,
    comment_id: str,
    file: UploadFile = File(...),
    requester: models.User = Depends(get_current_user),
):
    return {
        "data": await s_attachments.upload_attachment(
            ticket_id,
            comment_id,
            file,
            requester,
        )
    }


@router.get(
    "/{ticket_id}/comments/{comment_id}/attachments/{attachment_id}",
    status_code=200,
)
def download_comment_attachment(
    ticket_id: str,
    comment_id: str,
    attachment_id: str,
    requester: models.User = Depends(get_current_user),
):
    path, attachment, disposition = s_attachments.download_attachment(
        ticket_id,
        comment_id,
        attachment_id,
        requester,
    )
    return FileResponse(
        path,
        media_type=attachment.content_type,
        filename=None,
        headers={"Content-Disposition": disposition},
    )



@router.post("/{ticket_id}/analysis-results", status_code=202)
def request_ticket_analysis(
    ticket_id: str,
    requester: models.User = Depends(get_current_user),
):
    return {"data": s_analysis_results.request_analysis(ticket_id, requester)}


@router.get("/{ticket_id}/analysis-results", status_code=200)
def get_ticket_analysis_results(
    ticket_id: str,
    requester: models.User = Depends(get_current_user),
    limit: int = Query(constants.DEFAULT_PAGE_LIMIT, ge=1, le=constants.MAX_PAGE_LIMIT),
    offset: int = Query(0, ge=0),
):
    return {
        "data": s_analysis_results.get_ticket_analysis_results(
            ticket_id,
            requester,
            limit=limit,
            offset=offset,
        )
    }
