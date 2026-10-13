from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User

PAYLOAD = {"email": "a@x.com", "password": "password1"}


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
