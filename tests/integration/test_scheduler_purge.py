import asyncio

import pytest

from app import scheduler


@pytest.fixture
def calls(monkeypatch):
    c = {"tick": 0, "purge": 0}
    stop = asyncio.Event()

    async def fake_tick(*args, **kwargs):
        c["tick"] += 1
        if c["tick"] >= 3:
            stop.set()

    async def fake_purge(*args, **kwargs):
        c["purge"] += 1

    monkeypatch.setattr(scheduler, "run_tick", fake_tick)
    monkeypatch.setattr(scheduler, "run_purge", fake_purge)
    return c, stop


async def test_purge_runs_once_in_three_ticks(calls):
    c, stop = calls
    await scheduler.run_scheduler(None, None, stop, tick_seconds=0.01)
    assert c == {"tick": 3, "purge": 1}


async def test_purge_failure_keeps_loop_alive_and_is_not_retried(calls, monkeypatch):
    c, stop = calls

    async def boom(*args, **kwargs):
        c["purge"] += 1
        raise RuntimeError("db down")

    monkeypatch.setattr(scheduler, "run_purge", boom)
    await scheduler.run_scheduler(None, None, stop, tick_seconds=0.01)
    assert c == {"tick": 3, "purge": 1}


async def test_purge_uses_retention_days_setting(calls, monkeypatch):
    c, stop = calls
    seen = []

    async def spy(factory, now, days):
        seen.append(days)

    monkeypatch.setattr(scheduler, "run_purge", spy)
    await scheduler.run_scheduler(None, None, stop, tick_seconds=0.01)
    assert seen == [scheduler.get_settings().retention_days]
