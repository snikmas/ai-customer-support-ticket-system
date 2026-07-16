from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def add_agent_profile_last_assigned_at(engine: Engine) -> None:

    inspector = inspect(engine)
    if "agent_profiles" not in inspector.get_table_names():
        return
    column_names = {
        column["name"] for column in inspector.get_columns("agent_profiles")
    }
    if "last_assigned_at" in column_names:
        return

    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE agent_profiles ADD COLUMN last_assigned_at DATETIME")
        )
