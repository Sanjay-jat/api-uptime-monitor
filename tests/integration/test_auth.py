from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import User
from app.security import create_access_token, decode_access_token

PAYLOAD = {"email": "a@x.com", "password": "password1"}


async def _register(client):
    assert (await client.post("/auth/register", json=PAYLOAD)).status_code == 201


async def _token(client):
    await _register(client)
    r = await client.post("/auth/login", json=PAYLOAD)
    return r.json()["access_token"]


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


async def test_me_ok(client):
    token = await _token(client)
    r = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "a@x.com"
    assert "password_hash" not in body


async def test_me_missing_header(client):
    r = await client.get("/auth/me")

    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


async def test_me_wrong_scheme(client):
    r = await client.get(
        "/auth/me",
        headers={"Authorization": "Basic abc"},
    )

    assert r.status_code == 401


async def test_me_malformed_token(client):
    r = await client.get(
        "/auth/me",
        headers={"Authorization": "Bearer garbage"},
    )

    assert r.status_code == 401


async def test_me_expired_token(client):
    r = await client.post("/auth/register", json=PAYLOAD)
    uid = r.json()["id"]
    token = create_access_token(uid, timedelta(seconds=-1))
    r = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert r.status_code == 401


async def test_me_user_not_found(client):
    token = create_access_token(999999)
    r = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert r.status_code == 401


async def test_me_non_numeric_sub(client):
    s = get_settings()
    token = jwt.encode(
        {
            "sub": "abc",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        s.jwt_secret,
        algorithm=s.jwt_algorithm,
    )
    r = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert r.status_code == 401
