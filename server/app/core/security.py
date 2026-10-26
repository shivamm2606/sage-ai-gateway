from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import settings

hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        hasher.verify(password_hash, password)
        return True
    except VerifyMismatchError:
        return False


def create_access_token(user_id: int) -> str:
    # sub must be a string according to jwt spec
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        sub = payload.get("sub")
        if sub is None:
            return None
        return int(sub)
    except jwt.InvalidTokenError, ValueError:
        return None
