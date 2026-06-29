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
async def create_ticket(cur_ticket: models.TicketCreate, user_id: str):
    cur_id = constants.generate_id()
    now = datetime.now()

    is_user = db.get_user(user_id)
    print(f"check user id: {is_user}, type: {type(is_user)}")
    if is_user is None:
        raise HTTPException(404, detail="The user id doesn't exist")
    ticket = models.Ticket(id=cur_id, 
                    **cur_ticket.model_dump(), 
                    updated_at=datetime.now(), 
                    created_at=datetime.now(),
                    creator_user_id=is_user['id'],
                    due_at=now + timedelta(hours=2))

    ticket.category = str(ticket.category.value)
    ticket.tags = '[]'
    ticket.status = str(ticket.status.value)
    ticket.priority = str(ticket.priority.value)
    ticket.assigned_agent_id = ''


    db.insert_ticket(ticket.__dict__)
    return {"res": ticket}

@router.patch("/{ticket_id}", status_code=201)
async def update_ticket(new_info: models.TicketUpdate, ticket_id: str, requester_id: str):
    updated_info = new_info.model_dump(exclude_unset=True)

    if not updated_info:
        raise HTTPException(400, detail="No fields to update")
    
    # check the user: just users shouldn't be able change a ticket
    requester = db.get_user(requester_id)
    is_ticket = db.get_ticket(ticket_id)
    if is_ticket is None:
        raise HTTPException(404, "The Ticket not found")

    if requester is None:
        raise HTTPException(400, detail="No requester information")

    roles = constants.Roles
    if requester['role'] in [roles.USER.value, roles.GUEST.value, roles.BOT.value, roles.API.value]:
        raise HTTPException(403, detail="No rights to update a ticket")
    elif requester['role'] == roles.AGENT.value:
        if requester['id'] != is_ticket['assigned_agent_id']:
            raise HTTPException(403, detail="You don't have rights to update this ticket")
    
    if "assigned_agent_id" in updated_info.keys():
        if requester['role'] not in [roles.ADMIN.value, roles.MANAGER.value, roles.SUPER_ADMIN.value]:
            raise HTTPException(403, detail="No rights to update a ticket")
        
    if 'status' in updated_info.keys():
        new_status = constants.Status(updated_info['status'])
        if constants.is_valid_status_transition(is_ticket['status'], new_status) == False:
            raise HTTPException(409, detail="Invalid status field")
        assigned_agent = updated_info.get('assigned_agent_id') or is_ticket['assigned_agent_id'] or None
        if not assigned_agent:
            raise HTTPException(404, detail="For updating a ticket requires an agent id")
    

    affected_row = db.update_ticket(ticket_id, updated_info)
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