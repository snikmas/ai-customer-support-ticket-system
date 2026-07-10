from fastapi import APIRouter, HTTPException, Depends, Query
from src import models, db, constants
from src.services import users as s_users, tickets as s_tickets, comments as s_comments
from src.dependencies.auth import get_current_user
from src.exceptions.domain import AppException
from typing import Literal

router = APIRouter(
    prefix="/tickets",
    tags=["tickets"]
)

def _raise_http(exc: AppException):
    # Re-raise the domain error so the application-level handler keeps one
    # response shape for every router.
    raise exc

@router.get("/", status_code=200)
async def get_tickets(requester = Depends(get_current_user), 
                    limit: int = Query(constants.DEFAULT_PAGE_LIMIT, 
                                         ge=1,
                                         le=constants.MAX_PAGE_LIMIT),
                    offset: int = Query(0, ge=0),
                    sort_by: Literal['created_at', 'updated_at', 'status', 'priority'] = constants.DEFAULT_SORT_BY,
                    sort_order: Literal['asc', 'desc'] = constants.DEFAULT_SORT_ORDER,
                    priority: constants.Priority | None = None,
                    status: constants.Status | None = None
                    ):
    try:
        data = s_tickets.get_all_tickets(requester, limit, offset, sort_by, sort_order, priority, status)
    except PermissionError:
        raise HTTPException(400, detail="Permission Error")
    except ValueError:
        raise HTTPException(400, detail="Value Error")

    return {"data": data}


@router.get("/{id}", status_code=200)
async def get_ticket(id: str, requester = Depends(get_current_user)):
    try:    
        data = s_tickets.get_ticket(id, requester)
    except PermissionError:
        raise HTTPException(400, detail="Permission Error")
    except ValueError:
        raise HTTPException(400, detail="Value Error")

    return {"data": data}


@router.post("/", status_code=201)
async def create_ticket(cur_ticket: models.TicketCreate, requester = Depends(get_current_user)):
    
    ticket = s_tickets.create_ticket(cur_ticket, requester)
    
    return {"data": ticket}


@router.patch("/{ticket_id}", status_code=200)
async def update_ticket(ticket_id: str, new_info: models.TicketUpdate, requester = Depends(get_current_user)):
    
    try:
        data = s_tickets.update_ticket(ticket_id, new_info, requester)
    except PermissionError:
        raise HTTPException(400, detail="Permission Error")
    except ValueError:
        raise HTTPException(400, detail="Value Error")

    return {'data': data}

    
@router.delete("/{id}", status_code=200)
async def delete_ticket(id: str, requester = Depends(get_current_user)):

    try:
        data = s_tickets.delete_ticket(id, requester)
    except PermissionError:
        raise HTTPException(400, detail="Permission Error")
    except ValueError:
        raise HTTPException(400, detail="Value Error")
    
    return {'data': data}


@router.delete("/", status_code=200)
async def delete_all_tickets(requester = Depends(get_current_user)):

    try:
        data = s_tickets.delete_all_tickets(requester)
    except PermissionError:
        raise HTTPException(400, detail="Permission Error")
    
    return {'data': data}

@router.post("/{ticket_id}/claim", status_code=200)
async def claim_ticket(ticket_id: str, requester: models.User = Depends(get_current_user)):
    try:
        data = s_tickets.claim_ticket(ticket_id, requester)
    except PermissionError:
        raise HTTPException(403, detail="Permission Error")
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))
    
    return {'data': data}

@router.post("/{ticket_id}/assign", status_code=200)
async def assign_ticket(ticket_id: str, assign_ticket_req: models.AssignTicketRequest, requester: models.User = Depends(get_current_user)):
    try:
        data = s_tickets.assign_ticket(ticket_id, assign_ticket_req.agent_id, requester)
    except PermissionError:
        raise HTTPException(403, detail="Permission Error")
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))
    
    return {'data': data}


@router.get("/{ticket_id}/comments", status_code=200)
async def get_ticket_comments(
            ticket_id: str, 
            requester: models.User = Depends(get_current_user),
            limit: int = Query(constants.DEFAULT_PAGE_LIMIT, 
                                         ge=1,
                                         le=constants.MAX_PAGE_LIMIT),
            offset: int = Query(0, ge=0),
            sort_by: Literal['created_at', 'updated_at'] = 'created_at',
            sort_order: Literal['asc', 'desc'] = constants.DEFAULT_SORT_ORDER,
            ):
    try:
        data = s_comments.get_all_comments(ticket_id, requester, limit, offset, sort_by, sort_order)
    except AppException as exc:
        _raise_http(exc)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))

    return {"data": data}

@router.post("/{ticket_id}/comments", status_code=201)
async def create_ticket_comment(ticket_id: str, comment: models.CommentCreate, requester: models.User = Depends(get_current_user)):
    try:
        data = s_comments.create_ticket_comment(ticket_id, comment, requester)
    except AppException as exc:
        _raise_http(exc)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))

    return {"data": data}

@router.get("/{ticket_id}/comments/{comment_id}", status_code=200)
async def get_ticket_comment(ticket_id: str, comment_id: str, requester: models.User = Depends(get_current_user)):
    try:
        data = s_comments.get_comment(ticket_id, comment_id, requester)
    except AppException as exc:
        _raise_http(exc)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))

    return {"data": data}

@router.patch("/{ticket_id}/comments/{comment_id}", status_code=200)
async def update_ticket_comment(ticket_id: str, comment_id: str, new_info: models.CommentUpdate, requester: models.User = Depends(get_current_user)):
    try:
        data = s_comments.update_comment(ticket_id, comment_id, new_info, requester)
    except AppException as exc:
        _raise_http(exc)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))

    return {"data": data}

@router.delete("/{ticket_id}/comments/{comment_id}", status_code=200)
async def delete_ticket_comment(ticket_id: str, comment_id: str, requester: models.User = Depends(get_current_user)):
    try:
        data = s_comments.delete_comment(ticket_id, comment_id, requester)
    except AppException as exc:
        _raise_http(exc)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))

    return {"data": data}
