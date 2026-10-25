import hmac
import json
import socket
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.alerts import sign
from app.models import Endpoint, Incident, User
from app.scheduler import run_tick

API = "https://api.example.com/health"
HOOK = "https://hook.example.com/h"
SECRET = "s3cret"
T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def dns(monkeypatch):
    real = socket.getaddrinfo

    def fake(host, *args, **kwargs):
        if host in ("api.example.com", "hook.example.com"):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        return real(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake)


@pytest.fixture
async def http():
    async with httpx.AsyncClient(follow_redirects=False, timeout=None) as c:
        yield c


async def _setup(Session, with_webhook=True):
    async with Session() as s:
        user = User(
            email="a@example.com",
            password_hash="x",
            webhook_url=HOOK if with_webhook else None,
            webhook_secret=SECRET if with_webhook else None,
        )
        s.add(user)
        await s.flush()
        s.add(Endpoint(user_id=user.id, url=API, interval_seconds=60, next_check_at=T0))
        await s.commit()


async def _incidents(Session):
    async with Session() as s:
        return list((await s.scalars(select(Incident).order_by(Incident.id))).all())


async def test_full_outage_cycle_with_signed_alerts(engine, http, dns, respx_mock):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    await _setup(Session)
    respx_mock.get(API).mock(side_effect=[httpx.Response(500)] * 3 + [httpx.Response(200)])
    hook = respx_mock.post(HOOK).respond(200)

    # tick 1 aur 2: fail, par abhi DOWN nahi
    for i in range(2):
        await run_tick(Session, http, T0 + timedelta(hours=i))
    assert hook.call_count == 0
    assert await _incidents(Session) == []

    # tick 3: teesra fail, DOWN, incident khula, alert gaya
    await run_tick(Session, http, T0 + timedelta(hours=2))
    assert hook.call_count == 1
    req = hook.calls[0].request
    assert json.loads(req.content)["event"] == "went_down"
    assert json.loads(req.content)["url"] == API
    assert hmac.compare_digest(req.headers["x-signature"], "sha256=" + sign(SECRET, req.content))
    incs = await _incidents(Session)
    assert len(incs) == 1
    assert incs[0].opened_at == T0 + timedelta(hours=2)
    assert incs[0].resolved_at is None

    # tick 4: success, incident band, recovery alert
    await run_tick(Session, http, T0 + timedelta(hours=3))
    assert hook.call_count == 2
    assert json.loads(hook.calls[1].request.content)["event"] == "recovered"
    incs = await _incidents(Session)
    assert len(incs) == 1
    assert incs[0].resolved_at == T0 + timedelta(hours=3)


async def test_no_webhook_still_opens_incident_and_sends_nothing(engine, http, dns, respx_mock):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    await _setup(Session, with_webhook=False)
    respx_mock.get(API).respond(500)
    hook = respx_mock.post(HOOK).respond(200)

    for i in range(3):
        await run_tick(Session, http, T0 + timedelta(hours=i))

    assert hook.call_count == 0
    assert len(await _incidents(Session)) == 1


@pytest.mark.respx(assert_all_called=False)
async def test_webhook_500_does_not_stop_monitoring(engine, http, dns, respx_mock):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    await _setup(Session)
    respx_mock.get(API).mock(side_effect=[httpx.Response(500)] * 3 + [httpx.Response(200)])
    respx_mock.post(HOOK).respond(500)

    for i in range(4):
        await run_tick(Session, http, T0 + timedelta(hours=i))

    incs = await _incidents(Session)
    assert len(incs) == 1
    assert incs[0].resolved_at == T0 + timedelta(hours=3)
