from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.security import decode_access_token

PAYLOAD = {"email": "a@x.com", "password": "password1"}


async def _register(client):
    assert (await client.post("/auth/register", json=PAYLOAD)).status_code == 201


async def test_register_ok(client):
    r = await client.post("/auth/register", json=PAYLOAD)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "a@x.com"
    assert "password_hash" not in body
    assert "password" not in body


async def test_register_stores_hash(client, engine):
    assert (await client.post("/auth/register", json=PAYLOAD)).status_code == 201

    async with AsyncSession(engine) as s:
        user = (await s.execute(select(User))).scalar_one()

    assert user.password_hash != "password1"
    assert user.password_hash.startswith("$2")


async def test_register_duplicate_email(client):
    assert (await client.post("/auth/register", json=PAYLOAD)).status_code == 201
    r = await client.post("/auth/register", json=PAYLOAD)

    assert r.status_code == 409


async def test_register_duplicate_case_insensitive(client):
    assert (await client.post("/auth/register", json=PAYLOAD)).status_code == 201
    r = await client.post(
        "/auth/register",
        json={**PAYLOAD, "email": "A@X.com"},
    )

    assert r.status_code == 409


async def test_register_invalid_email(client):
    r = await client.post(
        "/auth/register",
        json={**PAYLOAD, "email": "nope"},
    )

    assert r.status_code == 422


async def test_register_short_password(client):
    r = await client.post(
        "/auth/register",
        json={**PAYLOAD, "password": "a" * 7},
    )

    assert r.status_code == 422


async def test_login_ok(client):
    await _register(client)
    r = await client.post("/auth/login", json=PAYLOAD)

    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert decode_access_token(body["access_token"])["sub"].isdigit()


async def test_login_wrong_password(client):
    await _register(client)
    r = await client.post(
        "/auth/login",
        json={**PAYLOAD, "password": "wrongpass1"},
    )

    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


async def test_login_unknown_email(client):
    r = await client.post(
        "/auth/login",
        json={**PAYLOAD, "email": "nobody@x.com"},
    )

    assert r.status_code == 401


async def test_login_error_messages_identical(client):
    await _register(client)
    r1 = await client.post(
        "/auth/login",
        json={**PAYLOAD, "password": "wrongpass1"},
    )
    r2 = await client.post(
        "/auth/login",
        json={**PAYLOAD, "email": "nobody@x.com"},
    )

    assert r1.json() == r2.json()


async def test_login_email_case_insensitive(client):
    await _register(client)
    r = await client.post(
        "/auth/login",
        json={**PAYLOAD, "email": "A@X.com"},
    )

    assert r.status_code == 200


async def test_login_malformed_body(client):
    r = await client.post("/auth/login", json={})

    assert r.status_code == 422
