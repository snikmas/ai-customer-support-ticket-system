from fastapi import FastAPI, APIRouter
from src.models.models import Ticket, Agent, Client, TicketCreate

router = APIRouter()
    
app = FastAPI()

@app.post("/ticket")
def create_ticket(ticket : TicketCreate):
    return {}


@app.get("/tickets")
def get_tickets():
    return {}