import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import cache
from app.db import get_db
from app.main import app
from app.ws import manager

PASSWORD = "password123"


@pytest.fixture
def tc(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    cache.clear()
    manager._conns.clear()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    cache.clear()
    manager._conns.clear()


def _user(tc, email):
    creds = {"email": email, "password": PASSWORD}
    tc.post("/auth/register", json=creds)
    token = tc.post("/auth/login", json=creds).json()["access_token"]
    uid = tc.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["id"]
    return token, uid


def _payload(endpoint_id, status="up"):
    return {"endpoint_id": endpoint_id, "status": status}


def test_valid_token_gets_snapshot_from_cache(tc):
    token, uid = _user(tc, "a@example.com")
    cache.set_status(uid, 1, _payload(1))
    cache.set_status(uid, 2, _payload(2, "down"))
    with tc.websocket_connect("/ws/dashboard") as ws:
        ws.send_json({"token": token})
        msg = ws.receive_json()
    assert msg["type"] == "snapshot"
    assert sorted(p["endpoint_id"] for p in msg["data"]) == [1, 2]


def test_empty_cache_gives_empty_snapshot(tc):
    token, _ = _user(tc, "a@example.com")
    with tc.websocket_connect("/ws/dashboard") as ws:
        ws.send_json({"token": token})
        assert ws.receive_json() == {"type": "snapshot", "data": []}


def test_snapshot_has_only_my_data(tc):
    token_a, uid_a = _user(tc, "a@example.com")
    _, uid_b = _user(tc, "b@example.com")
    cache.set_status(uid_a, 1, _payload(1))
    cache.set_status(uid_b, 2, _payload(2))
    with tc.websocket_connect("/ws/dashboard") as ws:
        ws.send_json({"token": token_a})
        data = ws.receive_json()["data"]
    assert [p["endpoint_id"] for p in data] == [1]


@pytest.mark.parametrize(
    "first_message",
    [
        {"token": "garbage"},
        {"token": 123},
        {"nothing": "here"},
        [1, 2, 3],
        "just a string",
    ],
)
def test_bad_first_message_closed_1008(tc, first_message):
    with tc.websocket_connect("/ws/dashboard") as ws:
        ws.send_json(first_message)
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 1008
    assert manager._conns == {}


def test_not_json_first_message_closed_1008(tc):
    with tc.websocket_connect("/ws/dashboard") as ws:
        ws.send_text("this is not json")
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 1008


def test_expired_token_closed_1008(tc):
    from datetime import timedelta

    from app.security import create_access_token

    _, uid = _user(tc, "a@example.com")
    old = create_access_token(uid, expires_delta=timedelta(minutes=-5))
    with tc.websocket_connect("/ws/dashboard") as ws:
        ws.send_json({"token": old})
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 1008


def test_token_of_unknown_user_closed_1008(tc):
    from app.security import create_access_token

    ghost = create_access_token(999999)
    with tc.websocket_connect("/ws/dashboard") as ws:
        ws.send_json({"token": ghost})
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 1008


def test_silent_client_times_out(tc, monkeypatch):
    monkeypatch.setattr("app.routers.dashboard.AUTH_TIMEOUT", 0.2)
    with tc.websocket_connect("/ws/dashboard") as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 1008


def test_socket_registered_while_open_and_removed_after(tc):
    token, uid = _user(tc, "a@example.com")
    with tc.websocket_connect("/ws/dashboard") as ws:
        ws.send_json({"token": token})
        ws.receive_json()
        assert len(manager._conns[uid]) == 1
    assert uid not in manager._conns


def test_two_sockets_of_same_user(tc):
    token, uid = _user(tc, "a@example.com")
    with tc.websocket_connect("/ws/dashboard") as ws1:
        ws1.send_json({"token": token})
        ws1.receive_json()
        with tc.websocket_connect("/ws/dashboard") as ws2:
            ws2.send_json({"token": token})
            ws2.receive_json()
            assert len(manager._conns[uid]) == 2
        assert len(manager._conns[uid]) == 1
    assert uid not in manager._conns


def test_client_messages_after_auth_are_ignored(tc):
    token, uid = _user(tc, "a@example.com")
    with tc.websocket_connect("/ws/dashboard") as ws:
        ws.send_json({"token": token})
        ws.receive_json()
        ws.send_text("not json, hello")
        ws.send_json({"anything": 1})
        assert len(manager._conns[uid]) == 1
    assert uid not in manager._conns
