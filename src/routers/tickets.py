from fastapi import APIRouter, Depends, Query
from src import models, db, constants
from src.services import users as s_users, tickets as s_tickets, comments as s_comments
from src.dependencies.auth import get_current_user
from typing import Literal

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
                    status: constants.Status | None = None
                    ):
    data = s_tickets.get_all_tickets(requester, limit, offset, sort_by, sort_order, priority, status)
    return {"data": data}


@router.get("/{id}", status_code=200)
def get_ticket(id: str, requester = Depends(get_current_user)):
    data = s_tickets.get_ticket(id, requester)
    return {"data": data}


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



@router.post("/{ticket_id}/analysis-jobs", status_code=200)
def analysis_job(ticket_id: str, requester: models.User = Depends(get_current_user)):
    data = s_tickets.analysis_job(ticket_id, requester)
    return data

@router.get("/{ticket_id}/analyse_ticket", status_code=200)
def get_analysis_job(ticket_id: str, requester: models.User = Depends(get_current_user)):
    data = s_tickets.get_analysis_job(ticket_id, requester)
    return data
