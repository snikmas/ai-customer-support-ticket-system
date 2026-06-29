from typing import Annotated
from fastapi import Depends

def get_current_user():
    pass

def require_admin():
    pass

#later put this function to another file
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()