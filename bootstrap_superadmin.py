# creating a superadmin during creation a db
import os

from dotenv import load_dotenv
from pydantic import ValidationError

from src.db import create_db
from src.models import UserCreate
from src.services.users import bootstrap_superadmin


ENV_FIELDS = {
    "nickname": "SUPERADMIN_NICKNAME",
    "first_name": "SUPERADMIN_FIRST_NAME",
    "last_name": "SUPERADMIN_LAST_NAME",
    "phone": "SUPERADMIN_PHONE",
    "email": "SUPERADMIN_EMAIL",
    "password": "SUPERADMIN_PASSWORD",
}


def main() -> int:
    load_dotenv()
    missing = [env_name for env_name in ENV_FIELDS.values() if not os.getenv(env_name)]
    if missing:
        print(f"Missing required environment variables: {', '.join(missing)}")
        return 2

    try:
        user_data = UserCreate(**{
            field: os.environ[env_name]
            for field, env_name in ENV_FIELDS.items()
        })
    except ValidationError as exc:
        print(f"Invalid superadmin configuration:\n{exc}")
        return 2

    create_db()
    if not bootstrap_superadmin(user_data):
        print("Bootstrap refused: the database already contains a user.")
        return 1

    print(f"Initial superadmin created: {user_data.nickname}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
