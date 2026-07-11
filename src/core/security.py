#password hashing jwt helpetrs ;ater
import bcrypt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from src.models import User
from datetime import datetime, timezone, timedelta
import jwt
import os
import hmac
import hashlib
import secrets


password_hasher = PasswordHasher()


def generate_refresh_token() -> str:
    raw_refresh_token = secrets.token_urlsafe(32)
    return raw_refresh_token

def hash_password(password: str) -> str:
    return password_hasher.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if hashed_password.startswith("$2"):
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        except ValueError:
            return False

    try:
        return password_hasher.verify(hashed_password, plain_password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def password_needs_rehash(hashed_password: str) -> bool:
    return hashed_password.startswith("$2") or password_hasher.check_needs_rehash(hashed_password)

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
