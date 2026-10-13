import asyncio

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import IntegrityError

from app.deps import DbSession
from app.models import User
from app.schemas import Credentials, UserOut
from app.security import hash_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
async def register(body: Credentials, db: DbSession) -> User:
    hashed = await asyncio.to_thread(hash_password, body.password)
    user = User(email=body.email, password_hash=hashed)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Email already registered") from None
    await db.refresh(user)
    return user
