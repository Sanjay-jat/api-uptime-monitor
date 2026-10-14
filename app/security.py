import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import get_settings


def create_access_token(user_id: int, expires_delta: timedelta | None = None) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    delta = expires_delta or timedelta(minutes=settings.access_token_minutes)

    payload = {"sub": str(user_id), "iat": now, "exp": now + delta}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "sub"]},
    )


def hash_password(plain: str) -> str:
    hashed = bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()
    return hashed


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
