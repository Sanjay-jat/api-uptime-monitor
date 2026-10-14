from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import User
from app.security import decode_access_token

bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_db)]


BearerCreds = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]


async def get_current_user(creds: BearerCreds, db: DbSession) -> User:
    unauthorized = HTTPException(
        status_code=401, detail="Not authenticated", headers={"WWW-Authenticate": "Bearer"}
    )
    if creds is None:
        raise unauthorized
    try:
        payload = decode_access_token(creds.credentials)
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, ValueError):
        raise unauthorized from None
    user = await db.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
