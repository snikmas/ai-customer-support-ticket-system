from src.models import LoginRequest, LoginResponse, User
from src import constants
from src.core.security import verify_password, create_access_token
from .permissions import check_for_access
from src.db import operations


# we dont ahve to return a user.. have
def login_user(identifier: str, password: str) -> User | None:
    if '@' in identifier: #its an email
        user = operations.get_user_by_email(identifier)
    else:
        user = operations.get_user_by_nickname(identifier)
    if user is None:
        return  None
    
    # check apssword
    validate_user = verify_password(password, user.password)
    if validate_user:
        return user
    raise ModuleNotFoundError

