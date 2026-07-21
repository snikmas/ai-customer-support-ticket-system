from sqlalchemy import create_engine, event
from src.core.config import DATABASE_ECHO, DATABASE_URL

engine = create_engine(DATABASE_URL, echo=DATABASE_ECHO)

if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
