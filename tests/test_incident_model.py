from datetime import datetime

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import Endpoint, Incident, User


async def _make_endpoint(session, email="a@example.com"):
    user = User(email=email, password_hash="x")
    session.add(user)
    await session.flush()
    ep = Endpoint(user_id=user.id, url="https://example.com", method="GET", interval_seconds=60)
    session.add(ep)
    await session.flush()
    return ep


async def test_second_open_incident_rejected(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        ep = await _make_endpoint(s)
        s.add(Incident(endpoint_id=ep.id))
        await s.commit()
        s.add(Incident(endpoint_id=ep.id))
        with pytest.raises(IntegrityError):
            await s.commit()


async def test_open_allowed_after_previous_closed(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        ep = await _make_endpoint(s)
        now = datetime.now().astimezone()
        s.add_all(
            [
                Incident(endpoint_id=ep.id, resolved_at=now),
                Incident(endpoint_id=ep.id, resolved_at=now),
                Incident(endpoint_id=ep.id),
            ]
        )
        await s.commit()
        count = await s.scalar(select(func.count()).select_from(Incident))
        assert count == 3


async def test_different_endpoints_can_both_be_open(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        ep1 = await _make_endpoint(s, "a@example.com")
        ep2 = await _make_endpoint(s, "b@example.com")
        s.add_all([Incident(endpoint_id=ep1.id), Incident(endpoint_id=ep2.id)])
        await s.commit()
        count = await s.scalar(select(func.count()).select_from(Incident))
        assert count == 2


async def test_opened_at_default_is_tz_aware(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        ep = await _make_endpoint(s)
        inc = Incident(endpoint_id=ep.id)
        s.add(inc)
        await s.commit()
        await s.refresh(inc)
        assert inc.opened_at.tzinfo is not None
        assert inc.resolved_at is None


async def test_deleting_endpoint_deletes_incidents(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        ep = await _make_endpoint(s)
        s.add(Incident(endpoint_id=ep.id))
        await s.commit()
        await s.execute(delete(Endpoint).where(Endpoint.id == ep.id))
        await s.commit()
        count = await s.scalar(select(func.count()).select_from(Incident))
        assert count == 0
