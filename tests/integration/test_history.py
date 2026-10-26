import socket
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import Incident, PingResult


@pytest.fixture
def public_dns(monkeypatch):
    real = socket.getaddrinfo

    def fake(host, *args, **kwargs):
        if host == "example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        return real(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake)


PASSWORD = "password123"


async def _auth(client, email):
    creds = {"email": email, "password": PASSWORD}
    await client.post("/auth/register", json=creds)
    r = await client.post("/auth/login", json=creds)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _make_endpoint(client, headers):
    r = await client.post(
        "/endpoints",
        json={"url": "https://example.com", "interval_seconds": 60},
        headers=headers,
    )
    assert r.status_code == 201
    return r.json()["id"]


async def _add_pings(engine, endpoint_id, count):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    base = datetime.now(UTC) - timedelta(hours=1)
    async with factory() as s:
        for i in range(count):
            up = i % 2 == 0
            s.add(
                PingResult(
                    endpoint_id=endpoint_id,
                    checked_at=base + timedelta(minutes=i),
                    ok=up,
                    status_code=200 if up else None,
                    response_ms=50 if up else None,
                    error=None if up else "timeout",
                )
            )
        await s.commit()


async def test_empty_history(client, public_dns):
    h = await _auth(client, "a@example.com")
    eid = await _make_endpoint(client, h)
    r = await client.get(f"/endpoints/{eid}/pings", headers=h)
    assert r.status_code == 200
    assert r.json() == []


async def test_newest_first_and_fields(client, engine, public_dns):
    h = await _auth(client, "a@example.com")
    eid = await _make_endpoint(client, h)
    await _add_pings(engine, eid, 3)
    body = (await client.get(f"/endpoints/{eid}/pings", headers=h)).json()
    assert len(body) == 3
    times = [p["checked_at"] for p in body]
    assert times == sorted(times, reverse=True)
    assert set(body[0]) == {"checked_at", "ok", "status_code", "response_ms", "error"}
    assert body[1]["ok"] is False
    assert body[1]["error"] == "timeout"


async def test_pagination_pages_cover_everything(client, engine, public_dns):
    h = await _auth(client, "a@example.com")
    eid = await _make_endpoint(client, h)
    await _add_pings(engine, eid, 5)
    url = f"/endpoints/{eid}/pings"
    full = (await client.get(url, headers=h)).json()
    p1 = (await client.get(url, params={"limit": 2, "offset": 0}, headers=h)).json()
    p2 = (await client.get(url, params={"limit": 2, "offset": 2}, headers=h)).json()
    p3 = (await client.get(url, params={"limit": 2, "offset": 4}, headers=h)).json()
    assert [len(p1), len(p2), len(p3)] == [2, 2, 1]
    assert p1 + p2 + p3 == full
    far = await client.get(url, params={"offset": 100}, headers=h)
    assert far.json() == []


@pytest.mark.parametrize("query", ["limit=0", "limit=201", "offset=-1"])
async def test_bounds_rejected(client, public_dns, query):
    h = await _auth(client, "a@example.com")
    eid = await _make_endpoint(client, h)
    r = await client.get(f"/endpoints/{eid}/pings?{query}", headers=h)
    assert r.status_code == 422


async def test_only_pings_of_that_endpoint(client, engine, public_dns):
    h = await _auth(client, "a@example.com")
    e1 = await _make_endpoint(client, h)
    e2 = await _make_endpoint(client, h)
    await _add_pings(engine, e1, 3)
    r = await client.get(f"/endpoints/{e2}/pings", headers=h)
    assert r.json() == []


async def test_other_user_gets_404_same_as_missing(client, engine, public_dns):
    ha = await _auth(client, "a@example.com")
    hb = await _auth(client, "b@example.com")
    eid = await _make_endpoint(client, ha)
    await _add_pings(engine, eid, 2)
    theirs = await client.get(f"/endpoints/{eid}/pings", headers=hb)
    missing = await client.get("/endpoints/999999/pings", headers=hb)
    assert theirs.status_code == 404
    assert missing.status_code == 404
    assert theirs.json() == missing.json()


async def test_requires_auth(client, public_dns):
    r = await client.get("/endpoints/1/pings")
    assert r.status_code == 401


async def _add_at(engine, endpoint_id, age, ok):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        s.add(
            PingResult(
                endpoint_id=endpoint_id,
                checked_at=datetime.now(UTC) - age,
                ok=ok,
                status_code=200 if ok else None,
                response_ms=50 if ok else None,
                error=None if ok else "timeout",
            )
        )
        await s.commit()


async def test_uptime_no_data_is_null_not_100(client, public_dns):
    h = await _auth(client, "a@example.com")
    eid = await _make_endpoint(client, h)
    r = await client.get(f"/endpoints/{eid}/uptime", headers=h)
    assert r.status_code == 200
    assert r.json() == {"window": "24h", "uptime_percent": None, "total_checks": 0}


async def test_uptime_known_fixture(client, engine, public_dns):
    h = await _auth(client, "a@example.com")
    eid = await _make_endpoint(client, h)
    for ok in (True, True, True, False):
        await _add_at(engine, eid, timedelta(hours=1), ok)
    body = (await client.get(f"/endpoints/{eid}/uptime", headers=h)).json()
    assert body == {"window": "24h", "uptime_percent": 75.0, "total_checks": 4}


async def test_uptime_window_filters_old_pings(client, engine, public_dns):
    h = await _auth(client, "a@example.com")
    eid = await _make_endpoint(client, h)
    await _add_at(engine, eid, timedelta(hours=1), True)
    await _add_at(engine, eid, timedelta(days=2), False)
    await _add_at(engine, eid, timedelta(days=40), False)
    url = f"/endpoints/{eid}/uptime"
    d1 = (await client.get(url, params={"window": "24h"}, headers=h)).json()
    d7 = (await client.get(url, params={"window": "7d"}, headers=h)).json()
    d30 = (await client.get(url, params={"window": "30d"}, headers=h)).json()
    assert (d1["total_checks"], d1["uptime_percent"]) == (1, 100.0)
    assert (d7["total_checks"], d7["uptime_percent"]) == (2, 50.0)
    assert (d30["total_checks"], d30["uptime_percent"]) == (2, 50.0)


async def test_uptime_counts_only_that_endpoint(client, engine, public_dns):
    h = await _auth(client, "a@example.com")
    e1 = await _make_endpoint(client, h)
    e2 = await _make_endpoint(client, h)
    await _add_at(engine, e1, timedelta(hours=1), False)
    body = (await client.get(f"/endpoints/{e2}/uptime", headers=h)).json()
    assert body["total_checks"] == 0


async def test_uptime_bad_window_422(client, public_dns):
    h = await _auth(client, "a@example.com")
    eid = await _make_endpoint(client, h)
    r = await client.get(f"/endpoints/{eid}/uptime?window=1y", headers=h)
    assert r.status_code == 422


async def test_uptime_other_user_404_same_as_missing(client, engine, public_dns):
    ha = await _auth(client, "a@example.com")
    hb = await _auth(client, "b@example.com")
    eid = await _make_endpoint(client, ha)
    theirs = await client.get(f"/endpoints/{eid}/uptime", headers=hb)
    missing = await client.get("/endpoints/999999/uptime", headers=hb)
    assert theirs.status_code == missing.status_code == 404
    assert theirs.json() == missing.json()


async def test_uptime_requires_auth(client, public_dns):
    assert (await client.get("/endpoints/1/uptime")).status_code == 401


async def _add_incident(engine, endpoint_id, age, duration=None):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    opened = datetime.now(UTC) - age
    async with factory() as s:
        s.add(
            Incident(
                endpoint_id=endpoint_id,
                opened_at=opened,
                resolved_at=opened + duration if duration else None,
            )
        )
        await s.commit()


async def test_incidents_empty(client, public_dns):
    h = await _auth(client, "a@example.com")
    eid = await _make_endpoint(client, h)
    r = await client.get(f"/endpoints/{eid}/incidents", headers=h)
    assert r.status_code == 200
    assert r.json() == []


async def test_incidents_newest_first_open_is_null(client, engine, public_dns):
    h = await _auth(client, "a@example.com")
    eid = await _make_endpoint(client, h)
    await _add_incident(engine, eid, timedelta(hours=3), timedelta(minutes=10))
    await _add_incident(engine, eid, timedelta(hours=2), timedelta(minutes=10))
    await _add_incident(engine, eid, timedelta(hours=1))  # abhi tak open
    body = (await client.get(f"/endpoints/{eid}/incidents", headers=h)).json()
    assert len(body) == 3
    opened = [i["opened_at"] for i in body]
    assert opened == sorted(opened, reverse=True)
    assert set(body[0]) == {"opened_at", "resolved_at"}
    assert body[0]["resolved_at"] is None
    assert body[1]["resolved_at"] is not None


async def test_incidents_pagination_covers_everything(client, engine, public_dns):
    h = await _auth(client, "a@example.com")
    eid = await _make_endpoint(client, h)
    for hours in range(1, 6):
        await _add_incident(engine, eid, timedelta(hours=hours), timedelta(minutes=5))
    url = f"/endpoints/{eid}/incidents"
    full = (await client.get(url, headers=h)).json()
    p1 = (await client.get(url, params={"limit": 2, "offset": 0}, headers=h)).json()
    p2 = (await client.get(url, params={"limit": 2, "offset": 2}, headers=h)).json()
    p3 = (await client.get(url, params={"limit": 2, "offset": 4}, headers=h)).json()
    assert [len(p1), len(p2), len(p3)] == [2, 2, 1]
    assert p1 + p2 + p3 == full


@pytest.mark.parametrize("query", ["limit=0", "limit=201", "offset=-1"])
async def test_incidents_bounds_rejected(client, public_dns, query):
    h = await _auth(client, "a@example.com")
    eid = await _make_endpoint(client, h)
    r = await client.get(f"/endpoints/{eid}/incidents?{query}", headers=h)
    assert r.status_code == 422


async def test_incidents_only_that_endpoint(client, engine, public_dns):
    h = await _auth(client, "a@example.com")
    e1 = await _make_endpoint(client, h)
    e2 = await _make_endpoint(client, h)
    await _add_incident(engine, e1, timedelta(hours=1))
    r = await client.get(f"/endpoints/{e2}/incidents", headers=h)
    assert r.json() == []


async def test_incidents_other_user_404_same_as_missing(client, engine, public_dns):
    ha = await _auth(client, "a@example.com")
    hb = await _auth(client, "b@example.com")
    eid = await _make_endpoint(client, ha)
    await _add_incident(engine, eid, timedelta(hours=1))
    theirs = await client.get(f"/endpoints/{eid}/incidents", headers=hb)
    missing = await client.get("/endpoints/999999/incidents", headers=hb)
    assert theirs.status_code == missing.status_code == 404
    assert theirs.json() == missing.json()


async def test_incidents_requires_auth(client, public_dns):
    assert (await client.get("/endpoints/1/incidents")).status_code == 401


async def test_timestamps_are_utc_aware(client, engine, public_dns):
    h = await _auth(client, "a@example.com")
    eid = await _make_endpoint(client, h)
    await _add_pings(engine, eid, 1)
    await _add_incident(engine, eid, timedelta(hours=1))
    ping = (await client.get(f"/endpoints/{eid}/pings", headers=h)).json()[0]
    inc = (await client.get(f"/endpoints/{eid}/incidents", headers=h)).json()[0]
    for value in (ping["checked_at"], inc["opened_at"]):
        parsed = datetime.fromisoformat(value)
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() == timedelta(0)
