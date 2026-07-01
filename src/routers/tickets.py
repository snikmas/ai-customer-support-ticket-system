from fastapi import APIRouter, HTTPException, Depends
from src import models, db, constants
from src.services import users as s_users, tickets as s_tickets
from src.dependencies import *

router = APIRouter(
    prefix="/tickets",
    tags=["tickets"]
)

@router.get("/", status_code=200)
async def get_tickets(requester = Depends(get_current_user)):
    try:
        data = s_tickets.get_all_tickets(requester)
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