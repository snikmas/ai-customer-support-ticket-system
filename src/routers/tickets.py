from fastapi import APIRouter, HTTPException
from src import models, db, constants
from datetime import datetime, timedelta

router = APIRouter(
    prefix="/tickets",
    tags=["tickets"]
)

@router.get("/")
async def get_tickets():
    db_res = db.get_tickets()
    all_tickets = []
    if db_res:
        for row in db_res:
            all_tickets.append(dict(row))
        return {"res": all_tickets}
    else:
        return {"res": "No tickets yet"}


@router.get("/{id}")
async def get_ticket(id: str):
    db_res = db.get_ticket(id)
    print(db_res)
    print(type(db_res))
    if not db_res: 
        raise HTTPException(404, detail="No ticket found")
    ticket = dict(db_res)
    
    return {"res": ticket}


@router.post("/", status_code=201)
async def create_ticket(cur_ticket: models.TicketCreate):
    # 1) generate an id 
    cur_id = constants.generate_id()

    now = datetime.now()
    ticket = models.Ticket(id=cur_id, 
                    **cur_ticket.model_dump(), 
                    updated_at=datetime.now(), 
                    created_at=datetime.now(),
                    due_at=now + timedelta(hours=2))

    ticket.category = str(ticket.category.value)
    ticket.tags = '[]'
    ticket.status = str(ticket.status.value)
    ticket.priority = str(ticket.priority.value)
    ticket.assigned_agent_id = ''
    print(ticket)
    db.insert_ticket(ticket.__dict__)
    return {"res": ticket}

@router.patch("/{id}", status_code=201)
async def update_ticket(new_info: models.TicketUpdate, id: str):
    updated_info = new_info.model_dump(exclude_unset=True)
    print(updated_info)

    if not updated_info:
        raise HTTPException(400, detail="No fields to update")
    
    affected_row = db.update_ticket(id, updated_info)
    if (affected_row == 0):
        raise HTTPException(400, detail="Error during updating")
    return {"res": "A ticket was updated successfully"}
    
@router.delete("/{id}")
async def delete_ticket(id: str):
    # we can frisly check if a ticket exist and later delete it? or check it using delete?
    affected_rows = db.delete_ticket(id)
    if affected_rows == 0:
        raise HTTPException(404, detail="No affected rows")
    return {"res": "A ticket was deleted successfully"}

@router.delete("/")
async def delete_all_tickets():
    res = db.delete_all_tickets()
    return {"res": f"{res} ticket(s) was deleted"}