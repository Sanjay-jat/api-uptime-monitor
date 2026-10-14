from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RefreshToken, User


def _expiry():
    return datetime.now(timezone.utc) + timedelta(days=7)


async def test_refresh_token_insert(engine):
    async with AsyncSession(engine) as s:
        user = User(email="a@x.com", password_hash="x")
        s.add(user)
        await s.flush()

        tok = RefreshToken(
            user_id=user.id,
            token_hash="h" * 64,
            expires_at=_expiry(),
        )
        s.add(tok)
        await s.commit()
        await s.refresh(tok)

        assert tok.id is not None
        assert tok.created_at is not None
        assert tok.revoked_at is None


async def test_token_hash_unique(engine):
    async with AsyncSession(engine) as s:
        user = User(email="a@x.com", password_hash="x")
        s.add(user)
        await s.flush()

        t1 = RefreshToken(
            user_id=user.id,
            token_hash="h" * 64,
            expires_at=_expiry(),
        )
        t2 = RefreshToken(
            user_id=user.id,
            token_hash="h" * 64,
            expires_at=_expiry(),
        )
        s.add_all([t1, t2])
        with pytest.raises(IntegrityError):
            await s.commit()


async def test_user_delete_cascades(engine):
    async with AsyncSession(engine) as s:
        user = User(email="a@x.com", password_hash="x")
        s.add(user)
        await s.flush()
        uid = user.id
        s.add(
            RefreshToken(
                user_id=uid,
                token_hash="h" * 64,
                expires_at=_expiry(),
            )
        )
        await s.commit()

        await s.execute(delete(User).where(User.id == uid))
        await s.commit()

        rows = (await s.execute(select(RefreshToken))).scalars().all()
        assert rows == []
