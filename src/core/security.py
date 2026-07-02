#password hashing jwt helpetrs ;ater
import bcrypt
from src.models import User
from datetime import datetime, timezone, timedelta
import jwt
import os
import hmac
import hashlib
import secrets

# is it used?
def generate_refresh_token() -> str:
    raw_refresh_token = secrets.token_urlsafe(32)
    return raw_refresh_token

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())

# for a refresh token
def hash_token(raw_token: str) -> str:
    secret = os.getenv('REFRESH_TOKEN_SECRET')

    if secret is None:
        raise RuntimeError("REFRESH_TOKEN_SECRET is not configured")
    
    return hmac.new(
        secret.encode('utf-8'),
        raw_token.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()


def create_access_token(user: User) -> str:

    now = datetime.now(timezone.utc)
    payload_data = {
        "sub": user.id,
        "role": user.role.value,
        "type": "access",
        "exp": now + timedelta(minutes=15),
        "iat": now
    }

    private_key_path = os.getenv("JWT_PRIVATE_KEY_PATH")
    algorithm = os.getenv("JWT_ALGORITHM")

    with open(private_key_path, 'r') as key_file:
        private_key = key_file.read()
    
    token = jwt.encode(
        payload_data,
        private_key,
        algorithm
    )

    return token

def decode_access_token(token: str) -> dict:
    public_key_path = os.getenv("JWT_PUBLIC_KEY_PATH")
    algorithm = os.getenv("JWT_ALGORITHM")

    with open(public_key_path, 'r') as key_file:
        public_key = key_file.read()

    payload = jwt.decode(
        token,
        public_key,
        algorithm
    )

    return payload
