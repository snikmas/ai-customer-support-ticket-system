from fastapi import FastAPI, APIRouter
from src.models.models import Ticket, Agent, Client, TicketCreate
from fastapi import HTTPException
from datetime import datetime, timedelta
from src.constants import helpers
import src.db.db as db
from src.routers import users, tickets

db.create_tables()


#i guess.. we should put all configuration to the oncfig file later

app = FastAPI()

app.include_router(users.router)
app.include_router(tickets.router)

@app.get("/")
async def root():
    return {"res": "hiiii"}
