from app.deps import get_current_user
from app.main import app

ORIGIN = "http://localhost:3000"
EVIL = "http://evil.test"


async def test_preflight_allowed_origin(client):
    r = await client.options(
        "/endpoints", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"}
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == ORIGIN


async def test_preflight_unknown_origin_rejected(client):
    r = await client.options(
        "/endpoints", headers={"Origin": EVIL, "Access-Control-Request-Method": "POST"}
    )
    assert r.status_code == 400
    assert "access-control-allow-origin" not in r.headers


async def test_allowed_origin_gets_header_and_exposes_request_id(client):
    r = await client.get("/health", headers={"Origin": ORIGIN})
    assert r.headers["access-control-allow-origin"] == ORIGIN
    assert "x-request-id" in r.headers["access-control-expose-headers"].lower()


async def test_unknown_origin_gets_no_cors_header(client):
    r = await client.get("/health", headers={"Origin": EVIL})
    assert r.status_code == 200
    assert "access-control-allow-origin" not in r.headers


async def test_credentials_not_allowed(client):
    r = await client.get("/health", headers={"Origin": ORIGIN})
    assert "access-control-allow-credentials" not in r.headers


async def test_cors_header_present_even_on_500(client):
    async def boom():
        raise RuntimeError("x")

    app.dependency_overrides[get_current_user] = boom
    try:
        r = await client.get("/auth/me", headers={"Origin": ORIGIN})
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert r.status_code == 500
    assert r.headers["access-control-allow-origin"] == ORIGIN
