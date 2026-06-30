from sqlalchemy import  create_engine
from pathlib import Path
from src.core.config import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=True)

