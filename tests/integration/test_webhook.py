import socket

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import User

URL = "https://example.com/hook"


@pytest.fixture
def public_dns(monkeypatch):
    real = socket.getaddrinfo

    def fake(host, *args, **kwargs):
        if host == "example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        return real(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake)


async def _auth(client, email="a@example.com"):
    creds = {"email": email, "password": "password123"}
    await client.post("/auth/register", json=creds)
    token = (await client.post("/auth/login", json=creds)).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _user_row(engine, email="a@example.com") -> User:
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        return (await s.execute(select(User).where(User.email == email))).scalar_one()


async def test_set_webhook_returns_url_and_secret(client, public_dns):
    h = await _auth(client)
    r = await client.put("/auth/me/webhook", json={"url": URL}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["webhook_url"] == URL
    assert len(body["webhook_secret"]) >= 32


async def test_set_webhook_saved_in_db(client, engine, public_dns):
    h = await _auth(client)
    body = (await client.put("/auth/me/webhook", json={"url": URL}, headers=h)).json()
    user = await _user_row(engine)
    assert user.webhook_url == URL
    assert user.webhook_secret == body["webhook_secret"]


async def test_set_again_rotates_secret(client, public_dns):
    h = await _auth(client)
    s1 = (await client.put("/auth/me/webhook", json={"url": URL}, headers=h)).json()
    s2 = (await client.put("/auth/me/webhook", json={"url": URL}, headers=h)).json()
    assert s1["webhook_secret"] != s2["webhook_secret"]


async def test_me_never_leaks_webhook(client, public_dns):
    h = await _auth(client)
    await client.put("/auth/me/webhook", json={"url": URL}, headers=h)
    me = (await client.get("/auth/me", headers=h)).json()
    assert "webhook_secret" not in me
    assert "webhook_url" not in me


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/hook",
        "https://user:pass@example.com/hook",
        "",
        "not-a-url",
        "https://example.com/" + "a" * 2050,
    ],
)
async def test_bad_url_is_422(client, public_dns, url):
    h = await _auth(client)
    r = await client.put("/auth/me/webhook", json={"url": url}, headers=h)
    assert r.status_code == 422


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1/hook", "http://localhost/hook", "http://169.254.169.254/x"],
)
async def test_private_url_is_422_and_not_saved(client, engine, public_dns, url):
    h = await _auth(client)
    r = await client.put("/auth/me/webhook", json={"url": url}, headers=h)
    assert r.status_code == 422
    user = await _user_row(engine)
    assert user.webhook_url is None
    assert user.webhook_secret is None


async def test_extra_field_is_422(client, public_dns):
    h = await _auth(client)
    r = await client.put("/auth/me/webhook", json={"url": URL, "webhook_secret": "mine"}, headers=h)
    assert r.status_code == 422


async def test_put_requires_auth(client):
    r = await client.put("/auth/me/webhook", json={"url": URL})
    assert r.status_code == 401


async def test_delete_clears_webhook(client, engine, public_dns):
    h = await _auth(client)
    await client.put("/auth/me/webhook", json={"url": URL}, headers=h)
    r = await client.delete("/auth/me/webhook", headers=h)
    assert r.status_code == 204
    user = await _user_row(engine)
    assert user.webhook_url is None
    assert user.webhook_secret is None


async def test_delete_without_webhook_is_204(client):
    h = await _auth(client)
    r = await client.delete("/auth/me/webhook", headers=h)
    assert r.status_code == 204


async def test_delete_requires_auth(client):
    r = await client.delete("/auth/me/webhook")
    assert r.status_code == 401


async def test_delete_touches_only_own_webhook(client, engine, public_dns):
    ha = await _auth(client, "a@example.com")
    hb = await _auth(client, "b@example.com")
    await client.put("/auth/me/webhook", json={"url": URL}, headers=ha)
    await client.put("/auth/me/webhook", json={"url": URL}, headers=hb)
    await client.delete("/auth/me/webhook", headers=ha)
    assert (await _user_row(engine, "a@example.com")).webhook_url is None
    assert (await _user_row(engine, "b@example.com")).webhook_url == URL


async def test_rate_limit_webhook_put_blocks_eleventh(client, public_dns, rate_on):
    h = await _auth(client)
    for _ in range(10):
        r = await client.put("/auth/me/webhook", json={"url": URL}, headers=h)
        assert r.status_code == 200
    r = await client.put("/auth/me/webhook", json={"url": URL}, headers=h)
    assert r.status_code == 429


async def test_rate_limit_webhook_put_is_per_user_not_per_ip(client, public_dns, rate_on):
    h1 = await _auth(client, "a@example.com")
    h2 = await _auth(client, "b@example.com")
    for _ in range(10):
        await client.put("/auth/me/webhook", json={"url": URL}, headers=h1)
    r = await client.put("/auth/me/webhook", json={"url": URL}, headers=h2)
    assert r.status_code == 200
