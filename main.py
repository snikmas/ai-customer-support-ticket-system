from fastapi import FastAPI, APIRouter
from src.models.models import Ticket, Agent, Client, TicketCreate
from fastapi import HTTPException
from datetime import datetime, timedelta
from src.constants import helpers
import logging
import src.db.db as db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db.create_tables()
logging.info("created tables")
#i guess.. we should put all configuration to the oncfig file later

router = APIRouter()

app = FastAPI()

@app.post("/tickets")
def create_ticket(cur_ticket : TicketCreate):
    # 1) generate an id 
    cur_id = helpers.generate_id()

    now = datetime.now()
    ticket = Ticket(id=cur_id, 
                    **cur_ticket.model_dump(), 
                    updated_at=datetime.now(), 
                    created_at=datetime.now(),
                    due_at=now + timedelta(hours=2))

    #check if its exists? id? its impossible, cmon
    #another problem do we have to save as id -> boejct (where we also put an id or?)
    # anyway, its doesnt matter really. later we would put everything to the database

    db.insert_data(ticket.__dict__, 'Tickets')
    return {"res": ticket}



@app.get("/tickets")
def get_tickets():
    # i guess we have to show only part of the infromation. again: from who this request?
    # if from user - not all. create model? but its != ticket create. let's firstly try to return all tickets with all info

    db_res = db.get_tickets()
    all_tickets = []
    for row in db_res:
        all_tickets.append(dict(row))

    return {"res": all_tickets}

@app.get("/tickets/{id}")
def get_ticket(id: str):
    db_res = db.get_tickets(id)
    ticket = dict(db_res)

    return {"res": ticket}