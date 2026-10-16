from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import RefreshToken, User
from app.security import create_access_token, decode_access_token, hash_refresh_token

PAYLOAD = {"email": "a@x.com", "password": "password1"}


async def _register(client):
    assert (await client.post("/auth/register", json=PAYLOAD)).status_code == 201


async def _token(client):
    await _register(client)
    r = await client.post("/auth/login", json=PAYLOAD)
    return r.json()["access_token"]


async def _login(client):
    await _register(client)
    return (await client.post("/auth/login", json=PAYLOAD)).json()


async def _refresh(client, token):
    return await client.post("/auth/refresh", json={"refresh_token": token})


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


async def test_login_returns_refresh_token(client):
    body = await _login(client)

    assert len(body["refresh_token"]) >= 43
    assert body["refresh_token"] != body["access_token"]


async def test_login_stores_hash_not_raw(client, engine):
    body = await _login(client)

    async with AsyncSession(engine) as s:
        rows = (await s.execute(select(RefreshToken))).scalars().all()

    assert len(rows) == 1
    assert rows[0].token_hash == hash_refresh_token(body["refresh_token"])
    assert rows[0].token_hash != body["refresh_token"]
    assert rows[0].revoked_at is None
    assert rows[0].expires_at > datetime.now(timezone.utc)


async def test_refresh_ok(client):
    first = await _login(client)
    r = await _refresh(client, first["refresh_token"])

    assert r.status_code == 200
    body = r.json()
    assert body["refresh_token"] != first["refresh_token"]

    me = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200


async def test_refresh_rotates_old_token(client, engine):
    first = await _login(client)
    r = await _refresh(client, first["refresh_token"])

    assert r.status_code == 200
    async with AsyncSession(engine) as s:
        rows = (await s.execute(select(RefreshToken))).scalars().all()

    assert len(rows) == 2
    by_hash = {row.token_hash: row for row in rows}
    assert by_hash[hash_refresh_token(first["refresh_token"])].revoked_at is not None
    remaining = [
        row
        for token_hash, row in by_hash.items()
        if token_hash != hash_refresh_token(first["refresh_token"])
    ]
    assert len(remaining) == 1
    assert remaining[0].revoked_at is None


async def test_refresh_reuse_revokes_all(client, engine):
    first = await _login(client)
    rotated = await _refresh(client, first["refresh_token"])
    assert rotated.status_code == 200
    second = rotated.json()

    reused = await _refresh(client, first["refresh_token"])
    assert reused.status_code == 401

    family_reuse = await _refresh(client, second["refresh_token"])
    assert family_reuse.status_code == 401

    async with AsyncSession(engine) as s:
        rows = (await s.execute(select(RefreshToken))).scalars().all()

    assert all(row.revoked_at is not None for row in rows)


async def test_refresh_unknown_token(client):
    r = await _refresh(client, "garbage")

    assert r.status_code == 401


async def test_refresh_expired_token(client, engine):
    first = await _login(client)

    async with AsyncSession(engine) as s:
        await s.execute(
            update(RefreshToken).values(
                expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)
            )
        )
        await s.commit()

    r = await _refresh(client, first["refresh_token"])
    assert r.status_code == 401


async def test_refresh_malformed_body(client):
    r = await client.post("/auth/refresh", json={})

    assert r.status_code == 422


async def test_reuse_does_not_touch_other_users(client, engine):
    a_tokens = await _login(client)
    assert (
        await client.post(
            "/auth/register",
            json={**PAYLOAD, "email": "b@x.com"},
        )
    ).status_code == 201
    b_tokens = (
        await client.post(
            "/auth/login",
            json={**PAYLOAD, "email": "b@x.com"},
        )
    ).json()

    assert (await _refresh(client, a_tokens["refresh_token"])).status_code == 200
    assert (await _refresh(client, a_tokens["refresh_token"])).status_code == 401
    assert (await _refresh(client, b_tokens["refresh_token"])).status_code == 200


async def test_two_logins_two_distinct_tokens(client, engine):
    await _register(client)
    first = (await client.post("/auth/login", json=PAYLOAD)).json()
    second = (await client.post("/auth/login", json=PAYLOAD)).json()

    assert first["refresh_token"] != second["refresh_token"]

    async with AsyncSession(engine) as s:
        rows = (await s.execute(select(RefreshToken))).scalars().all()

    assert len(rows) == 2


async def test_failed_login_creates_no_token(client, engine):
    await _register(client)
    response = await client.post(
        "/auth/login",
        json={**PAYLOAD, "password": "wrongpass1"},
    )

    assert response.status_code == 401

    async with AsyncSession(engine) as s:
        rows = (await s.execute(select(RefreshToken))).scalars().all()

    assert rows == []


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
