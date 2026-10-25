import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import Endpoint, PingResult, User
from app.monitor import CheckResult
from app.scheduler import run_scheduler

OK = CheckResult(ok=True, status_code=200, response_ms=5, error=None)


@pytest.fixture()
def factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def test_loop_pings_due_endpoint_then_stops(factory, monkeypatch):
    pinged = asyncio.Event()

    async def _ping(*args, **kwargs):
        pinged.set()
        return OK

    monkeypatch.setattr("app.scheduler.ping", _ping)
    async with factory() as s:
        user = User(email="a@example.com", password_hash="x")
        s.add(user)
        await s.flush()
        s.add(
            Endpoint(
                user_id=user.id,
                url="https://a.example.com",
                interval_seconds=60,
                next_check_at=datetime(2000, 1, 1, tzinfo=UTC),
            )
        )
        await s.commit()

    stop = asyncio.Event()
    task = asyncio.create_task(run_scheduler(factory, None, stop, tick_seconds=0.01))
    await asyncio.wait_for(pinged.wait(), timeout=5)
    stop.set()
    await asyncio.wait_for(task, timeout=5)

    async with factory() as s:
        count = (await s.execute(select(func.count(PingResult.id)))).scalar_one()
    assert count == 1


async def test_stop_set_before_start_runs_no_tick(factory, monkeypatch):
    calls = 0

    async def _tick(*args, **kwargs):
        nonlocal calls
        calls += 1

    monkeypatch.setattr("app.scheduler.run_tick", _tick)
    stop = asyncio.Event()
    stop.set()
    await asyncio.wait_for(run_scheduler(factory, None, stop), timeout=1)

    assert calls == 0


async def test_tick_error_does_not_kill_loop(factory, monkeypatch):
    calls = 0
    second_tick = asyncio.Event()

    async def _tick(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("db down")
        second_tick.set()

    monkeypatch.setattr("app.scheduler.run_tick", _tick)
    stop = asyncio.Event()
    task = asyncio.create_task(run_scheduler(factory, None, stop, tick_seconds=0.01))
    await asyncio.wait_for(second_tick.wait(), timeout=5)
    stop.set()
    await asyncio.wait_for(task, timeout=5)

    assert calls >= 2


async def test_stop_wakes_loop_without_waiting_full_tick(factory, monkeypatch):
    ticked = asyncio.Event()

    async def _tick(*args, **kwargs):
        ticked.set()

    monkeypatch.setattr("app.scheduler.run_tick", _tick)
    stop = asyncio.Event()
    task = asyncio.create_task(run_scheduler(factory, None, stop, tick_seconds=60))
    await asyncio.wait_for(ticked.wait(), timeout=5)
    stop.set()
    await asyncio.wait_for(task, timeout=1)
