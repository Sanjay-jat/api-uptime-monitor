from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import Endpoint, PingResult, User
from app.monitor import CheckResult, Event
from app.scheduler import check_endpoint

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
OK = CheckResult(ok=True, status_code=200, response_ms=42, error=None)
FAIL = CheckResult(ok=False, status_code=None, response_ms=None, error="timeout")


@pytest.fixture()
def fake_ping(monkeypatch):
    results: list[CheckResult] = []

    async def _ping(*args, **kwargs):
        return results.pop(0)

    monkeypatch.setattr("app.scheduler.ping", _ping)
    return results


async def _make_endpoint(session) -> Endpoint:
    user = User(email="a@example.com", password_hash="x")
    session.add(user)
    await session.flush()
    ep = Endpoint(
        user_id=user.id,
        url="https://a.example.com",
        interval_seconds=60,
        next_check_at=NOW,
    )
    session.add(ep)
    await session.flush()
    return ep


async def test_success_saves_ping_and_schedules_next(engine, fake_ping):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    fake_ping.append(OK)
    async with Session() as s:
        ep = await _make_endpoint(s)
        event = await check_endpoint(s, None, ep, NOW)
        ep_id = ep.id

    async with Session() as s:
        row = (await s.execute(select(PingResult))).scalar_one()
        saved = await s.get(Endpoint, ep_id)

    assert event == Event.NONE
    assert row.ok is True
    assert row.status_code == 200
    assert row.response_ms == 42
    assert row.error is None
    assert row.checked_at == NOW
    assert saved.fail_count == 0
    assert saved.status == "up"
    assert NOW + timedelta(seconds=60) <= saved.next_check_at <= NOW + timedelta(seconds=66)


async def test_down_only_after_threshold_failures(engine, fake_ping):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    fake_ping.extend([FAIL, FAIL, FAIL])
    async with Session() as s:
        ep = await _make_endpoint(s)
        e1 = await check_endpoint(s, None, ep, NOW)
        e2 = await check_endpoint(s, None, ep, NOW)
        assert (ep.fail_count, ep.status) == (2, "up")
        e3 = await check_endpoint(s, None, ep, NOW)
        ep_id = ep.id

    async with Session() as s:
        saved = await s.get(Endpoint, ep_id)
        pings = (await s.execute(select(PingResult))).scalars().all()

    assert [e1, e2, e3] == [Event.NONE, Event.NONE, Event.WENT_DOWN]
    assert saved.status == "down"
    assert len(pings) == 3
    assert all(p.ok is False and p.error == "timeout" for p in pings)


async def test_success_after_down_recovers(engine, fake_ping):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    fake_ping.extend([FAIL, FAIL, FAIL, OK])
    async with Session() as s:
        ep = await _make_endpoint(s)
        for _ in range(3):
            await check_endpoint(s, None, ep, NOW)
        event = await check_endpoint(s, None, ep, NOW)

    assert event == Event.RECOVERED
    assert ep.status == "up"
    assert ep.fail_count == 0


async def test_one_failure_then_success_resets_counter(engine, fake_ping):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    fake_ping.extend([FAIL, OK])
    async with Session() as s:
        ep = await _make_endpoint(s)
        await check_endpoint(s, None, ep, NOW)
        event = await check_endpoint(s, None, ep, NOW)

    assert event == Event.NONE
    assert ep.fail_count == 0
    assert ep.status == "up"


async def test_threshold_param_is_used(engine, fake_ping):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    fake_ping.append(FAIL)
    async with Session() as s:
        ep = await _make_endpoint(s)
        event = await check_endpoint(s, None, ep, NOW, threshold=1)

    assert event == Event.WENT_DOWN
    assert ep.status == "down"


async def test_no_open_transaction_while_pinging(engine, monkeypatch):
    """An open transaction holds a pooled DB connection during the slow ping."""
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        seen = []

        async def _ping(*args, **kwargs):
            seen.append(s.in_transaction())
            return OK

        monkeypatch.setattr("app.scheduler.ping", _ping)
        ep = await _make_endpoint(s)
        await check_endpoint(s, None, ep, NOW)

    assert seen == [False]
