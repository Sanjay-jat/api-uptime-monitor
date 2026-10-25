from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import Endpoint, User
from app.monitor import CheckResult
from app.scheduler import run_tick

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
OK = CheckResult(ok=True, status_code=200, response_ms=5, error=None)


@pytest.fixture()
def factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture()
def pinged(monkeypatch):
    urls: list[str] = []

    async def _ping(client, url, *args, **kwargs):
        urls.append(url)
        return OK

    monkeypatch.setattr("app.scheduler.ping", _ping)
    return urls


async def _seed(factory, specs):
    """specs: (name, interval_seconds, next_check_at)."""
    async with factory() as s:
        user = User(email="a@example.com", password_hash="x")
        s.add(user)
        await s.flush()
        s.add_all(
            Endpoint(
                user_id=user.id,
                url=f"https://{name}.example.com",
                interval_seconds=interval,
                next_check_at=due,
            )
            for name, interval, due in specs
        )
        await s.commit()


async def _next_checks(factory) -> dict[str, datetime]:
    async with factory() as s:
        rows = (await s.execute(select(Endpoint))).scalars().all()
    return {e.url.split("//")[1].split(".")[0]: e.next_check_at for e in rows}


async def test_each_endpoint_uses_its_own_interval(factory, pinged):
    due = NOW - timedelta(seconds=10)
    await _seed(factory, [("fast", 60, due), ("slow", 300, due)])

    await run_tick(factory, None, NOW)
    nxt = await _next_checks(factory)
    assert NOW + timedelta(seconds=60) <= nxt["fast"] <= NOW + timedelta(seconds=66)
    assert NOW + timedelta(seconds=300) <= nxt["slow"] <= NOW + timedelta(seconds=330)

    pinged.clear()
    await run_tick(factory, None, NOW + timedelta(seconds=100))
    assert pinged == ["https://fast.example.com"]


async def test_overdue_endpoint_after_restart_pings_once_not_a_burst(factory, pinged):
    await _seed(factory, [("a", 60, NOW - timedelta(days=1))])

    await run_tick(factory, None, NOW)
    nxt = (await _next_checks(factory))["a"]
    assert NOW + timedelta(seconds=60) <= nxt <= NOW + timedelta(seconds=66)

    await run_tick(factory, None, NOW)
    await run_tick(factory, None, NOW + timedelta(seconds=30))
    assert pinged == ["https://a.example.com"]

    await run_tick(factory, None, NOW + timedelta(seconds=70))
    assert pinged == ["https://a.example.com", "https://a.example.com"]
