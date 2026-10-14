import asyncio

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.deps import CurrentUser, DbSession
from app.models import User
from app.schemas import Credentials, TokenOut, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

DUMMY_HASH = hash_password("dummy-password")


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


@router.post("/login", response_model=TokenOut)
async def login(body: Credentials, db: DbSession) -> TokenOut:
    user = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    hashed = user.password_hash if user else DUMMY_HASH
    ok = await asyncio.to_thread(verify_password, body.password, hashed)
    if not user or not ok:
        raise HTTPException(
            status_code=401, detail="Invalid Credentials", headers={"WWW-Authenticate": "Bearer"}
        )
    return TokenOut(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
async def me(current_user: CurrentUser) -> User:
    return current_user
