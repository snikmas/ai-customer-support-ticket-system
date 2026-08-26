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

    token = jwt.encode(
        payload_data,
        _load_jwt_key("JWT_PRIVATE_KEY_PATH", "private.pem"),
        _jwt_algorithm()
    )

    return token

def decode_access_token(token: str) -> dict:
    payload = jwt.decode(
        token,
        _load_jwt_key("JWT_PUBLIC_KEY_PATH", "public.pem"),
        _jwt_algorithm()
    )

    return payload


# --- JWT key loading -------------------------------------------------------
# Keys are read once per process instead of on every token create/verify, and
# default to the project keys/ directory so local runs outside Docker work
# without extra environment setup.
_JWT_KEY_CACHE: dict[str, str] = {}


def _jwt_algorithm() -> str:
    return os.getenv("JWT_ALGORITHM", "RS256")


def _load_jwt_key(env_var: str, default_filename: str) -> str:
    from pathlib import Path

    path = os.getenv(env_var)
    if not path:
        path = str(
            Path(__file__).resolve().parent.parent.parent / "keys" / default_filename
        )
    if path not in _JWT_KEY_CACHE:
        try:
            with open(path, 'r') as key_file:
                _JWT_KEY_CACHE[path] = key_file.read()
        except OSError as exc:
            raise RuntimeError(
                f"JWT key file is not readable: {path} "
                f"(set {env_var} to override)"
            ) from exc
    return _JWT_KEY_CACHE[path]
