import socket
from datetime import UTC, datetime

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import cache
from app.models import Endpoint
from app.scheduler import check_endpoint

PASSWORD = "password123"
URL = "https://example.com"


@pytest.fixture
def public_dns(monkeypatch):
    real = socket.getaddrinfo

    def fake(host, *args, **kwargs):
        if host == "example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        return real(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake)


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


class FakeManager:
    def __init__(self):
        self.calls = []

    async def broadcast(self, user_id, message):
        self.calls.append((user_id, message))


@pytest.fixture
def fake_manager(monkeypatch):
    fake = FakeManager()
    monkeypatch.setattr("app.scheduler.manager", fake)
    return fake


async def _user(client, email):
    creds = {"email": email, "password": PASSWORD}
    await client.post("/auth/register", json=creds)
    token = (await client.post("/auth/login", json=creds)).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    uid = (await client.get("/auth/me", headers=headers)).json()["id"]
    return headers, uid


async def _endpoint(client, headers):
    r = await client.post("/endpoints", json={"url": URL, "interval_seconds": 60}, headers=headers)
    assert r.status_code == 201
    return r.json()["id"]


async def _check(engine, endpoint_id, status_code, threshold=3):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, httpx.AsyncClient() as http:
        ep = await session.get(Endpoint, endpoint_id)
        with respx.mock:
            respx.get(URL).mock(return_value=httpx.Response(status_code))
            await check_endpoint(session, http, ep, datetime.now(UTC), threshold)


async def test_successful_ping_fills_cache_and_broadcasts(client, engine, public_dns, fake_manager):
    headers, uid = await _user(client, "a@example.com")
    eid = await _endpoint(client, headers)
    await _check(engine, eid, 200)
    [entry] = cache.get_user_statuses(uid)
    assert entry["endpoint_id"] == eid
    assert entry["status"] == "up"
    assert entry["ok"] is True
    assert entry["status_code"] == 200
    assert isinstance(entry["checked_at"], str)
    assert len(fake_manager.calls) == 1
    user_id, message = fake_manager.calls[0]
    assert user_id == uid
    assert message == {"type": "update", "data": entry}


async def test_failed_ping_below_threshold_is_ok_false_but_still_up(
    client, engine, public_dns, fake_manager
):
    headers, uid = await _user(client, "a@example.com")
    eid = await _endpoint(client, headers)
    await _check(engine, eid, 500)
    [entry] = cache.get_user_statuses(uid)
    assert entry["ok"] is False
    assert entry["status_code"] == 500
    assert entry["status"] == "up"


async def test_confirmed_down_shows_down(client, engine, public_dns, fake_manager):
    headers, uid = await _user(client, "a@example.com")
    eid = await _endpoint(client, headers)
    await _check(engine, eid, 500, threshold=1)
    [entry] = cache.get_user_statuses(uid)
    assert entry["status"] == "down"


async def test_second_check_replaces_cache_entry(client, engine, public_dns, fake_manager):
    headers, uid = await _user(client, "a@example.com")
    eid = await _endpoint(client, headers)
    await _check(engine, eid, 200)
    await _check(engine, eid, 500, threshold=1)
    [entry] = cache.get_user_statuses(uid)
    assert entry["status"] == "down"
    assert len(fake_manager.calls) == 2


async def test_commit_failure_publishes_nothing(
    client, engine, public_dns, fake_manager, monkeypatch
):
    headers, uid = await _user(client, "a@example.com")
    eid = await _endpoint(client, headers)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, httpx.AsyncClient() as http:
        ep = await session.get(Endpoint, eid)

        async def boom():
            raise RuntimeError("db down")

        monkeypatch.setattr(session, "commit", boom)
        with respx.mock:
            respx.get(URL).mock(return_value=httpx.Response(200))
            with pytest.raises(RuntimeError):
                await check_endpoint(session, http, ep, datetime.now(UTC))
    assert cache.get_user_statuses(uid) == []
    assert fake_manager.calls == []


async def test_delete_endpoint_clears_cache(client, public_dns):
    headers, uid = await _user(client, "a@example.com")
    e1 = await _endpoint(client, headers)
    e2 = await _endpoint(client, headers)
    cache.set_status(uid, e1, {"endpoint_id": e1})
    cache.set_status(uid, e2, {"endpoint_id": e2})
    r = await client.delete(f"/endpoints/{e1}", headers=headers)
    assert r.status_code == 204
    assert cache.get_user_statuses(uid) == [{"endpoint_id": e2}]


async def test_other_users_delete_is_404_and_keeps_cache(client, public_dns):
    ha, uid_a = await _user(client, "a@example.com")
    hb, _ = await _user(client, "b@example.com")
    eid = await _endpoint(client, ha)
    cache.set_status(uid_a, eid, {"endpoint_id": eid})
    r = await client.delete(f"/endpoints/{eid}", headers=hb)
    assert r.status_code == 404
    assert cache.get_user_statuses(uid_a) == [{"endpoint_id": eid}]
