from . import models
from .engine import engine
from .migrations import (
    add_agent_profile_last_assigned_at,
    add_ticket_department_id,
    add_ticket_due_at,
    backfill_legacy_departments,
    migrate_analysis_result_contract,
    migrate_event_actor_contract,
)
from sqlalchemy import text
from sqlalchemy.orm import Session
from src.constants import utc_now

def create_db() -> None:
    models.Base.metadata.create_all(engine)
    with Session(engine) as session:
        if session.get(models.AISetting, "global") is None:
            now = utc_now()
            session.add(models.AISetting(
                id="global",
                provider="fake",
                model="deterministic-fake-v1",
                version=1,
                updated_by_user_id=None,
                created_at=now,
                updated_at=now,
            ))
            session.commit()
    add_agent_profile_last_assigned_at(engine)
    add_ticket_due_at(engine)
    add_ticket_department_id(engine)
    backfill_legacy_departments(engine)
    migrate_event_actor_contract(engine)
    migrate_analysis_result_contract(engine)


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
