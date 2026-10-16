import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.deps import CurrentUser, DbSession
from app.models import RefreshToken, User
from app.schemas import Credentials, RefreshIn, TokenOut, UserOut
from app.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

DUMMY_HASH = hash_password("dummy-password")


async def _issue_tokens(db: AsyncSession, user_id: int) -> TokenOut:
    raw = generate_refresh_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=get_settings().refresh_token_days)
    db.add(RefreshToken(user_id=user_id, token_hash=hash_refresh_token(raw), expires_at=expires_at))
    await db.commit()
    return TokenOut(access_token=create_access_token(user_id), refresh_token=raw)


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
    return await _issue_tokens(db, user.id)


@router.get("/me", response_model=UserOut)
async def me(current_user: CurrentUser) -> User:
    return current_user


@router.post("/refresh", response_model=TokenOut)
async def refresh(body: RefreshIn, db: DbSession) -> TokenOut:
    invalid = HTTPException(
        status_code=401, detail="Invalid refresh token", headers={"WWW-Authenticate": "Bearer"}
    )
    token_hash = hash_refresh_token(body.refresh_token)
    row = (
        await db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
        )
    ).scalar_one_or_none()
    if not row:
        raise invalid
    now = datetime.now(timezone.utc)
    if row.revoked_at is not None:
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == row.user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await db.commit()
        raise invalid
    if row.expires_at <= now:
        raise invalid
    row.revoked_at = now
    return await _issue_tokens(db, row.user_id)


@router.post("/logout", status_code=204)
async def logout(body: RefreshIn, db: DbSession) -> None:
    await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == hash_refresh_token(body.refresh_token),
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(timezone.utc))
    )
    await db.commit()
