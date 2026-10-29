import asyncio
import socket
from types import SimpleNamespace

import pytest


@pytest.fixture
def public_dns(monkeypatch):
    real = socket.getaddrinfo

    def fake(host, *args, **kwargs):
        if host == "example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        return real(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake)


async def make_user(client, email):
    creds = {"email": email, "password": "password123"}
    await client.post("/auth/register", json=creds)
    r = await client.post("/auth/login", json=creds)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


BODY = {"url": "https://example.com", "interval_seconds": 300}


async def test_create_returns_201_and_hides_user_id(client, public_dns):
    h = await make_user(client, "a@example.com")
    r = await client.post("/endpoints", json=BODY, headers=h)
    assert r.status_code == 201
    data = r.json()
    assert data["url"] == "https://example.com"
    assert data["method"] == "GET"
    assert data["is_active"] is True
    assert "user_id" not in data
    assert data["next_check_at"] and data["created_at"]


async def test_create_requires_auth(client, public_dns):
    r = await client.post("/endpoints", json=BODY)
    assert r.status_code == 401


async def test_list_requires_auth(client):
    r = await client.get("/endpoints")
    assert r.status_code == 401


async def test_create_private_ip_rejected(client):
    h = await make_user(client, "a@example.com")
    r = await client.post("/endpoints", json={**BODY, "url": "http://127.0.0.1"}, headers=h)
    assert r.status_code == 422


async def test_create_bad_interval_rejected(client, public_dns):
    h = await make_user(client, "a@example.com")
    r = await client.post("/endpoints", json={**BODY, "interval_seconds": 10}, headers=h)
    assert r.status_code == 422


async def test_create_user_id_in_body_rejected(client, public_dns):
    h = await make_user(client, "a@example.com")
    r = await client.post("/endpoints", json={**BODY, "user_id": 999}, headers=h)
    assert r.status_code == 422


async def test_list_empty_returns_empty_list(client):
    h = await make_user(client, "a@example.com")
    r = await client.get("/endpoints", headers=h)
    assert r.status_code == 200
    assert r.json() == []


async def test_list_shows_only_own_endpoints(client, public_dns):
    ha = await make_user(client, "a@example.com")
    hb = await make_user(client, "b@example.com")
    await client.post("/endpoints", json=BODY, headers=ha)
    mine = await client.get("/endpoints", headers=ha)
    theirs = await client.get("/endpoints", headers=hb)
    assert len(mine.json()) == 1
    assert theirs.json() == []


async def create_ep(client, h, **over):
    r = await client.post("/endpoints", json={**BODY, **over}, headers=h)
    assert r.status_code == 201
    return r.json()


async def test_get_own_endpoint(client, public_dns):
    h = await make_user(client, "a@example.com")
    ep = await create_ep(client, h)
    r = await client.get(f"/endpoints/{ep['id']}", headers=h)
    assert r.status_code == 200
    assert r.json() == ep


async def test_get_requires_auth(client):
    r = await client.get("/endpoints/1")
    assert r.status_code == 401


async def test_get_other_users_endpoint_is_404(client, public_dns):
    ha = await make_user(client, "a@example.com")
    hb = await make_user(client, "b@example.com")
    ep = await create_ep(client, ha)
    r = await client.get(f"/endpoints/{ep['id']}", headers=hb)
    assert r.status_code == 404


async def test_get_missing_looks_same_as_other_users(client, public_dns):
    ha = await make_user(client, "a@example.com")
    hb = await make_user(client, "b@example.com")
    ep = await create_ep(client, ha)
    other = await client.get(f"/endpoints/{ep['id']}", headers=hb)
    missing = await client.get("/endpoints/999999", headers=hb)
    assert other.status_code == missing.status_code == 404
    assert other.json() == missing.json()


async def test_get_non_numeric_id_rejected(client):
    h = await make_user(client, "a@example.com")
    r = await client.get("/endpoints/abc", headers=h)
    assert r.status_code == 422


async def test_patch_changes_interval(client, public_dns):
    h = await make_user(client, "a@example.com")
    ep = await create_ep(client, h)
    r = await client.patch(f"/endpoints/{ep['id']}", json={"interval_seconds": 600}, headers=h)
    assert r.status_code == 200
    assert r.json()["interval_seconds"] == 600


async def test_patch_leaves_other_fields_alone(client, public_dns):
    h = await make_user(client, "a@example.com")
    ep = await create_ep(client, h, method="HEAD", timeout_seconds=20)
    r = await client.patch(f"/endpoints/{ep['id']}", json={"is_active": False}, headers=h)
    data = r.json()
    assert data["is_active"] is False
    assert data["method"] == "HEAD"
    assert data["timeout_seconds"] == 20
    assert data["interval_seconds"] == 300


async def test_patch_empty_body_changes_nothing(client, public_dns):
    h = await make_user(client, "a@example.com")
    ep = await create_ep(client, h)
    r = await client.patch(f"/endpoints/{ep['id']}", json={}, headers=h)
    assert r.status_code == 200
    assert r.json() == ep


async def test_patch_other_users_endpoint_is_404_and_unchanged(client, public_dns):
    ha = await make_user(client, "a@example.com")
    hb = await make_user(client, "b@example.com")
    ep = await create_ep(client, ha)
    r = await client.patch(f"/endpoints/{ep['id']}", json={"interval_seconds": 600}, headers=hb)
    assert r.status_code == 404
    mine = await client.get(f"/endpoints/{ep['id']}", headers=ha)
    assert mine.json()["interval_seconds"] == 300


async def test_patch_private_url_rejected(client, public_dns):
    h = await make_user(client, "a@example.com")
    ep = await create_ep(client, h)
    r = await client.patch(f"/endpoints/{ep['id']}", json={"url": "http://127.0.0.1"}, headers=h)
    assert r.status_code == 422
    mine = await client.get(f"/endpoints/{ep['id']}", headers=h)
    assert mine.json()["url"] == "https://example.com"


async def test_patch_bad_url_on_other_users_endpoint_is_404(client, public_dns):
    ha = await make_user(client, "a@example.com")
    hb = await make_user(client, "b@example.com")
    ep = await create_ep(client, ha)
    r = await client.patch(f"/endpoints/{ep['id']}", json={"url": "http://127.0.0.1"}, headers=hb)
    assert r.status_code == 404


async def test_patch_bad_input_rejected(client, public_dns):
    h = await make_user(client, "a@example.com")
    ep = await create_ep(client, h)
    for body in ({"interval_seconds": 10}, {"user_id": 5}, {"method": "POST"}):
        r = await client.patch(f"/endpoints/{ep['id']}", json=body, headers=h)
        assert r.status_code == 422


async def test_delete_own_endpoint(client, public_dns):
    h = await make_user(client, "a@example.com")
    ep = await create_ep(client, h)
    r = await client.delete(f"/endpoints/{ep['id']}", headers=h)
    assert r.status_code == 204
    assert (await client.get(f"/endpoints/{ep['id']}", headers=h)).status_code == 404
    assert (await client.get("/endpoints", headers=h)).json() == []


async def test_delete_twice_second_is_404(client, public_dns):
    h = await make_user(client, "a@example.com")
    ep = await create_ep(client, h)
    assert (await client.delete(f"/endpoints/{ep['id']}", headers=h)).status_code == 204
    assert (await client.delete(f"/endpoints/{ep['id']}", headers=h)).status_code == 404


async def test_delete_other_users_endpoint_is_404_and_kept(client, public_dns):
    ha = await make_user(client, "a@example.com")
    hb = await make_user(client, "b@example.com")
    ep = await create_ep(client, ha)
    r = await client.delete(f"/endpoints/{ep['id']}", headers=hb)
    assert r.status_code == 404
    assert (await client.get(f"/endpoints/{ep['id']}", headers=ha)).status_code == 200


@pytest.fixture
def cap_2(monkeypatch):
    monkeypatch.setattr(
        "app.routers.endpoints.get_settings",
        lambda: SimpleNamespace(max_endpoints_per_user=2),
    )


async def test_create_over_limit_is_403(client, public_dns, cap_2):
    h = await make_user(client, "a@example.com")
    await create_ep(client, h)
    await create_ep(client, h)
    r = await client.post("/endpoints", json=BODY, headers=h)
    assert r.status_code == 403
    assert "2" in r.json()["detail"]
    assert len((await client.get("/endpoints", headers=h)).json()) == 2


async def test_limit_is_per_user(client, public_dns, cap_2):
    ha = await make_user(client, "a@example.com")
    hb = await make_user(client, "b@example.com")
    await create_ep(client, ha)
    await create_ep(client, ha)
    await create_ep(client, hb)


async def test_delete_frees_a_slot(client, public_dns, cap_2):
    h = await make_user(client, "a@example.com")
    first = await create_ep(client, h)
    await create_ep(client, h)
    assert (await client.delete(f"/endpoints/{first['id']}", headers=h)).status_code == 204
    await create_ep(client, h)


async def test_parallel_creates_cannot_exceed_limit(client, public_dns, cap_2):
    h = await make_user(client, "a@example.com")
    results = await asyncio.gather(
        *[client.post("/endpoints", json=BODY, headers=h) for _ in range(6)]
    )
    codes = sorted(r.status_code for r in results)
    assert codes == [201, 201, 403, 403, 403, 403]
    assert len((await client.get("/endpoints", headers=h)).json()) == 2


async def test_rate_limit_create_blocks_eleventh(client, public_dns, cap_2, rate_on):
    h = await make_user(client, "a@example.com")
    for _ in range(10):
        r = await client.post("/endpoints", json=BODY, headers=h)
        assert r.status_code in (201, 403)
    r = await client.post("/endpoints", json=BODY, headers=h)
    assert r.status_code == 429


async def test_rate_limit_create_is_per_user_not_per_ip(client, public_dns, cap_2, rate_on):
    ha = await make_user(client, "a@example.com")
    hb = await make_user(client, "b@example.com")
    for _ in range(10):
        await client.post("/endpoints", json=BODY, headers=ha)
    r = await client.post("/endpoints", json=BODY, headers=ha)
    assert r.status_code == 429
    r = await client.post("/endpoints", json=BODY, headers=hb)
    assert r.status_code == 201


async def test_rate_limit_patch_blocks_eleventh(client, public_dns, rate_on):
    h = await make_user(client, "a@example.com")
    ep = await create_ep(client, h)
    url = f"/endpoints/{ep['id']}"
    for _ in range(10):
        r = await client.patch(url, json={"interval_seconds": 120}, headers=h)
        assert r.status_code == 200
    r = await client.patch(url, json={"interval_seconds": 120}, headers=h)
    assert r.status_code == 429


async def test_rate_limit_patch_is_per_user_not_per_ip(client, public_dns, rate_on):
    ha = await make_user(client, "a@example.com")
    hb = await make_user(client, "b@example.com")
    ep = await create_ep(client, ha)
    url = f"/endpoints/{ep['id']}"
    for _ in range(10):
        await client.patch(url, json={"interval_seconds": 120}, headers=ha)
    r = await client.patch(url, json={"interval_seconds": 120}, headers=hb)
    assert r.status_code == 404
