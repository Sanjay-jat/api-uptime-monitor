from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import Endpoint, PingResult, User
from app.scheduler import purge_old_pings

NOW = datetime(2026, 1, 31, tzinfo=UTC)


@pytest.fixture
def factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def make_endpoint(session):
    user = User(email=f"{uuid4().hex}@example.com", password_hash="x")
    session.add(user)
    await session.flush()
    ep = Endpoint(
        user_id=user.id,
        url="https://example.com",
        method="GET",
        interval_seconds=60,
    )
    session.add(ep)
    await session.commit()
    return ep


async def _seed(session, ages_days):
    ep = await make_endpoint(session)
    session.add_all(
        PingResult(endpoint_id=ep.id, ok=True, checked_at=NOW - timedelta(days=d))
        for d in ages_days
    )
    await session.commit()


async def _count(session):
    return await session.scalar(select(func.count()).select_from(PingResult))


async def test_old_removed_recent_kept(factory):
    async with factory() as s:
        await _seed(s, [40, 31, 1, 0])
        assert await purge_old_pings(s, NOW, days=30) == 2
        assert await _count(s) == 2


async def test_exactly_cutoff_is_kept(factory):
    async with factory() as s:
        await _seed(s, [30])
        assert await purge_old_pings(s, NOW, days=30) == 0
        assert await _count(s) == 1


async def test_many_batches(factory):
    async with factory() as s:
        await _seed(s, [40] * 5)
        assert await purge_old_pings(s, NOW, days=30, batch=2) == 5
        assert await _count(s) == 0


async def test_rows_equal_batch_size(factory):
    async with factory() as s:
        await _seed(s, [40, 40])
        assert await purge_old_pings(s, NOW, days=30, batch=2) == 2
        assert await _count(s) == 0


async def test_empty_table(factory):
    async with factory() as s:
        assert await purge_old_pings(s, NOW, days=30) == 0
