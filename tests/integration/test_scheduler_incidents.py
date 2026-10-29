from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import Endpoint, Incident, User
from app.monitor import CheckResult, Event
from app.scheduler import check_endpoint

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
OK = CheckResult(ok=True, status_code=200, response_ms=42, error=None)
FAIL = CheckResult(ok=False, status_code=None, response_ms=None, error="timeout")
OLD_OPEN = datetime(2025, 12, 1, 8, 0, tzinfo=UTC)
OLD_CLOSE = datetime(2025, 12, 1, 9, 0, tzinfo=UTC)


@pytest.fixture()
def fake_ping(monkeypatch):
    results: list[CheckResult] = []

    async def _ping(*args, **kwargs):
        return results.pop(0)

    monkeypatch.setattr("app.scheduler.ping", _ping)
    return results


async def _make_endpoint(session, email="a@example.com", **kw) -> Endpoint:
    user = User(email=email, password_hash="x")
    session.add(user)
    await session.flush()
    ep = Endpoint(
        user_id=user.id,
        url="https://a.example.com",
        interval_seconds=60,
        next_check_at=NOW,
        **kw,
    )
    session.add(ep)
    await session.flush()
    return ep


async def _incidents(Session) -> list[Incident]:
    # new session: the UPDATE runs as raw SQL, an old session would show stale objects
    async with Session() as s:
        return list((await s.scalars(select(Incident).order_by(Incident.id))).all())


async def test_went_down_opens_incident(engine, fake_ping):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    fake_ping.append(FAIL)
    async with Session() as s:
        ep = await _make_endpoint(s)
        event = await check_endpoint(s, None, ep, NOW, threshold=1)
        ep_id = ep.id

    incs = await _incidents(Session)
    assert event == Event.WENT_DOWN
    assert len(incs) == 1
    assert incs[0].endpoint_id == ep_id
    assert incs[0].opened_at == NOW
    assert incs[0].resolved_at is None


async def test_below_threshold_opens_nothing(engine, fake_ping):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    fake_ping.append(FAIL)
    async with Session() as s:
        ep = await _make_endpoint(s)
        event = await check_endpoint(s, None, ep, NOW, threshold=3)

    assert event == Event.NONE
    assert await _incidents(Session) == []


async def test_success_on_healthy_endpoint_opens_nothing(engine, fake_ping):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    fake_ping.append(OK)
    async with Session() as s:
        ep = await _make_endpoint(s)
        event = await check_endpoint(s, None, ep, NOW)

    assert event == Event.NONE
    assert await _incidents(Session) == []


async def test_recovered_closes_incident(engine, fake_ping):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    fake_ping.append(OK)
    async with Session() as s:
        ep = await _make_endpoint(s, status="down", fail_count=3)
        s.add(Incident(endpoint_id=ep.id))
        await s.commit()
        event = await check_endpoint(s, None, ep, NOW)

    incs = await _incidents(Session)
    assert event == Event.RECOVERED
    assert len(incs) == 1
    assert incs[0].resolved_at == NOW


async def test_recovery_closes_only_own_incident(engine, fake_ping):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    fake_ping.append(OK)
    async with Session() as s:
        ep1 = await _make_endpoint(s, "a@example.com", status="down", fail_count=3)
        ep2 = await _make_endpoint(s, "b@example.com", status="down", fail_count=3)
        s.add_all([Incident(endpoint_id=ep1.id), Incident(endpoint_id=ep2.id)])
        await s.commit()
        await check_endpoint(s, None, ep1, NOW)
        ids = (ep1.id, ep2.id)

    by_ep = {i.endpoint_id: i for i in await _incidents(Session)}
    assert by_ep[ids[0]].resolved_at == NOW
    assert by_ep[ids[1]].resolved_at is None


async def test_one_incident_per_outage(engine, fake_ping):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    fake_ping.extend([FAIL, FAIL, OK, FAIL])
    async with Session() as s:
        ep = await _make_endpoint(s)
        events = [await check_endpoint(s, None, ep, NOW, threshold=1) for _ in range(4)]

    incs = await _incidents(Session)
    assert events == [Event.WENT_DOWN, Event.NONE, Event.RECOVERED, Event.WENT_DOWN]
    assert len(incs) == 2
    assert incs[0].resolved_at == NOW
    assert incs[1].resolved_at is None


async def test_recovery_does_not_touch_old_closed_incident(engine, fake_ping):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    fake_ping.extend([FAIL, OK])
    async with Session() as s:
        ep = await _make_endpoint(s)
        s.add(Incident(endpoint_id=ep.id, opened_at=OLD_OPEN, resolved_at=OLD_CLOSE))
        await s.flush()
        await check_endpoint(s, None, ep, NOW, threshold=1)
        event = await check_endpoint(s, None, ep, NOW, threshold=1)

    incs = await _incidents(Session)
    assert event == Event.RECOVERED
    assert len(incs) == 2
    assert incs[0].resolved_at == OLD_CLOSE
    assert incs[1].resolved_at == NOW
