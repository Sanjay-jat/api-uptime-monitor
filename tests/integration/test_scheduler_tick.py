import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import Endpoint, PingResult, User
from app.monitor import CheckResult
from app.scheduler import _check_one, run_tick

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
    """specs: (name, seconds_from_now, is_active). Returns {name: endpoint_id}."""
    async with factory() as s:
        user = User(email="a@example.com", password_hash="x")
        s.add(user)
        await s.flush()
        eps = {
            name: Endpoint(
                user_id=user.id,
                url=f"https://{name}.example.com",
                interval_seconds=60,
                next_check_at=NOW + timedelta(seconds=delta),
                is_active=active,
            )
            for name, delta, active in specs
        }
        s.add_all(eps.values())
        await s.commit()
        return {name: ep.id for name, ep in eps.items()}


async def _ping_count(factory) -> int:
    async with factory() as s:
        return (await s.execute(select(func.count(PingResult.id)))).scalar_one()


async def test_tick_pings_only_due_active_endpoints(factory, pinged):
    await _seed(
        factory,
        [("due1", -10, True), ("due2", -1, True), ("future", 60, True), ("paused", -10, False)],
    )
    await run_tick(factory, None, NOW)

    assert sorted(pinged) == ["https://due1.example.com", "https://due2.example.com"]
    assert await _ping_count(factory) == 2


async def test_second_tick_does_not_reping(factory, pinged):
    await _seed(factory, [("a", -10, True)])
    await run_tick(factory, None, NOW)
    await run_tick(factory, None, NOW)

    assert pinged == ["https://a.example.com"]
    assert await _ping_count(factory) == 1


async def test_one_failing_endpoint_does_not_stop_others(factory, monkeypatch):
    ids = await _seed(factory, [("bad", -10, True), ("good", -10, True)])

    async def _ping(client, url, *args, **kwargs):
        if "bad" in url:
            raise RuntimeError("boom")
        return OK

    monkeypatch.setattr("app.scheduler.ping", _ping)
    await run_tick(factory, None, NOW)

    async with factory() as s:
        rows = (await s.execute(select(PingResult))).scalars().all()
    assert [r.endpoint_id for r in rows] == [ids["good"]]


async def test_concurrency_is_capped(factory, monkeypatch):
    await _seed(factory, [(f"e{i}", -10, True) for i in range(5)])
    running = 0
    peak = 0

    async def _ping(client, url, *args, **kwargs):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.05)
        running -= 1
        return OK

    monkeypatch.setattr("app.scheduler.ping", _ping)
    await run_tick(factory, None, NOW, max_concurrency=2)

    assert peak == 2
    assert await _ping_count(factory) == 5


async def test_check_one_skips_paused_and_missing(factory, pinged):
    ids = await _seed(factory, [("paused", -10, False)])
    sem = asyncio.Semaphore(1)

    await _check_one(factory, None, ids["paused"], NOW, 3, sem)
    await _check_one(factory, None, 999999, NOW, 3, sem)

    assert pinged == []
    assert await _ping_count(factory) == 0
