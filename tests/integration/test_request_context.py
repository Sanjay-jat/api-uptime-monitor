import json
import logging

from app.deps import get_current_user
from app.main import app


def _access_records(caplog):
    return [r for r in caplog.records if r.name == "app.access"]


async def test_every_response_has_request_id(client):
    r = await client.get("/health")
    assert r.headers["x-request-id"]


async def test_request_ids_are_unique(client):
    a = await client.get("/health")
    b = await client.get("/health")
    assert a.headers["x-request-id"] != b.headers["x-request-id"]


async def test_error_response_has_request_id(client):
    r = await client.get("/auth/me")
    assert r.status_code == 401
    assert r.headers["x-request-id"]


async def test_access_log_line_fields(client, caplog):
    with caplog.at_level(logging.INFO, logger="app.access"):
        r = await client.get("/health")
    data = json.loads(_access_records(caplog)[-1].getMessage())
    assert data["event"] == "request"
    assert data["method"] == "GET"
    assert data["path"] == "/health"
    assert data["status"] == 200
    assert data["duration_ms"] >= 0
    assert data["request_id"] == r.headers["x-request-id"]


async def test_log_does_not_contain_query_string(client, caplog):
    with caplog.at_level(logging.INFO, logger="app.access"):
        await client.get("/health?token=supersecret")
    lines = " ".join(r.getMessage() for r in _access_records(caplog))
    assert lines
    assert "supersecret" not in lines


async def test_unhandled_error_is_generic_500(client, caplog):
    async def boom():
        raise RuntimeError("secret-internal-detail")

    app.dependency_overrides[get_current_user] = boom
    try:
        r = await client.get("/auth/me")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    body = r.json()
    assert r.status_code == 500
    assert body["detail"] == "Internal server error"
    assert body["request_id"] == r.headers["x-request-id"]
    assert "secret-internal-detail" not in r.text
    assert "Traceback" not in r.text
    errors = [x for x in caplog.records if x.levelno == logging.ERROR]
    assert body["request_id"] in errors[0].getMessage()
    assert "secret-internal-detail" in caplog.text
