import asyncio
import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import Endpoint, Incident, User
from app.monitor import CheckResult, Event
from app.scheduler import _alert, _check_one

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
HOOK = "https://hook.example.com/h"
SECRET = "s3cret"
FAIL = CheckResult(ok=False, status_code=None, response_ms=None, error="timeout")


@pytest.fixture()
def sent(monkeypatch):
    calls: list[tuple] = []

    async def _send(client, url, secret, body):
        calls.append((url, secret, json.loads(body)))
        return True

    monkeypatch.setattr("app.scheduler.send_webhook", _send)
    return calls


@pytest.fixture()
def fake_ping(monkeypatch):
    results: list[CheckResult] = []

    async def _ping(*args, **kwargs):
        return results.pop(0)

    monkeypatch.setattr("app.scheduler.ping", _ping)
    return results


async def _make_endpoint(session, url=HOOK, secret=SECRET) -> Endpoint:
    user = User(email="a@example.com", password_hash="x", webhook_url=url, webhook_secret=secret)
    session.add(user)
    await session.flush()
    ep = Endpoint(
        user_id=user.id,
        url="https://api.example.com/health",
        interval_seconds=60,
        next_check_at=NOW,
    )
    session.add(ep)
    await session.flush()
    return ep


@pytest.mark.parametrize("event", [Event.WENT_DOWN, Event.RECOVERED])
async def test_alert_sends_signed_payload(engine, sent, event):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        ep = await _make_endpoint(s)
        await _alert(s, None, ep, event, NOW)

    assert len(sent) == 1
    url, secret, body = sent[0]
    assert url == HOOK
    assert secret == SECRET
    assert body["event"] == event.value
    assert body["endpoint_id"] == ep.id
    assert body["url"] == "https://api.example.com/health"  # monitored URL, not the webhook


async def test_alert_skips_event_none(engine, sent):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        ep = await _make_endpoint(s)
        await _alert(s, None, ep, Event.NONE, NOW)
    assert sent == []


@pytest.mark.parametrize(("url", "secret"), [(None, None), (HOOK, None), (None, SECRET), ("", "")])
async def test_alert_skips_when_webhook_not_fully_set(engine, sent, url, secret):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        ep = await _make_endpoint(s, url=url, secret=secret)
        await _alert(s, None, ep, Event.WENT_DOWN, NOW)
    assert sent == []


async def test_check_one_alerts_after_commit(engine, sent, fake_ping):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    fake_ping.append(FAIL)
    async with Session() as s:
        ep = await _make_endpoint(s)
        await s.commit()
        ep_id = ep.id

    await _check_one(Session, None, ep_id, NOW, 1, asyncio.Semaphore(1))

    assert len(sent) == 1
    assert sent[0][2]["event"] == "went_down"
    async with Session() as s:
        incs = (await s.scalars(select(Incident))).all()
    assert len(incs) == 1


async def test_check_one_no_alert_below_threshold(engine, sent, fake_ping):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    fake_ping.append(FAIL)
    async with Session() as s:
        ep = await _make_endpoint(s)
        await s.commit()
        ep_id = ep.id

    await _check_one(Session, None, ep_id, NOW, 3, asyncio.Semaphore(1))
    assert sent == []


async def test_webhook_crash_keeps_incident_and_does_not_raise(engine, monkeypatch, fake_ping):
    async def boom(*args, **kwargs):
        raise RuntimeError("webhook exploded")

    monkeypatch.setattr("app.scheduler.send_webhook", boom)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    fake_ping.append(FAIL)
    async with Session() as s:
        ep = await _make_endpoint(s)
        await s.commit()
        ep_id = ep.id

    await _check_one(Session, None, ep_id, NOW, 1, asyncio.Semaphore(1))  # no raise

    async with Session() as s:
        saved = await s.get(Endpoint, ep_id)
        incs = (await s.scalars(select(Incident))).all()
    assert saved.status == "down"
    assert len(incs) == 1
