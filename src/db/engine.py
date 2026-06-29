from sqlalchemy import  create_engine
import os
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
db_file = root_dir / "tickets_system.db"


database_url = f'sqlite+pysqlite://{db_file}'
engine = create_engine(database_url, echo=True)

