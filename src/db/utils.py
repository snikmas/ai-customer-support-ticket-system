from . import models
from db.engine import engine

def create_db() -> None:
    models.Base.metadata.create_all(engine)

def drop_db() -> None:
    models.Base.metadata.drop_all(engine)

def reset_database() -> None:
    drop_db()
    create_db()