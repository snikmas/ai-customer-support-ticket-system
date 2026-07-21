from . import models
from .engine import engine
from .migrations import add_agent_profile_last_assigned_at, add_ticket_due_at
from sqlalchemy import text

def create_db() -> None:
    models.Base.metadata.create_all(engine)
    add_agent_profile_last_assigned_at(engine)
    add_ticket_due_at(engine)


def ping_database() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

def drop_db() -> None:
    models.Base.metadata.drop_all(engine)

def reset_database() -> None:
    drop_db()
    create_db()
