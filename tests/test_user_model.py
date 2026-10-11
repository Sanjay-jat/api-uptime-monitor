import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def test_user_insert(engine):
    async with AsyncSession(engine) as session:
        user = User(email="abc@g.com", password_hash="123456")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        assert user.id is not None
        assert user.created_at is not None


async def test_duplicate_email_rejected(engine):
    async with AsyncSession(engine) as session:
        user1 = User(email="abc@g.com", password_hash="123456")
        user2 = User(email="abc@g.com", password_hash="654321")
        session.add(user1)
        session.add(user2)
        with pytest.raises(IntegrityError):
            await session.commit()
