from sqlalchemy import  create_engine
import os
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
db_file = root_dir / "tickets_system.db"


database_url = f'sqlite+pysqlite:////{db_file}'

engine = create_engine(database_url, echo=True)


if __name__ == "__main__":
    print(database_url)

# sqlite+pysqlite:////absolute/path/to/file.db

# sqlite+pysqlite:///home/snikmas/work/projects/internship_project/tickets_system.db