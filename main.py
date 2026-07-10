from fastapi import FastAPI, APIRouter
from fastapi import HTTPException
from datetime import datetime, timedelta
from src.constants import helpers
from src.routers import users, tickets, auth, jobs
from src.db.utils import create_db
from src.core import setup_logging
from dotenv import load_dotenv
import os

load_dotenv()

# later convert to startup/lifespan
create_db()
setup_logging()


#i guess.. we should put all configuration to the oncfig file later

app = FastAPI()

app.include_router(users.router)
app.include_router(tickets.router)
app.include_router(auth.router)
app.include_router(jobs.router)

@app.get("/")
async def root():
    return {"res": "hiiii"}
