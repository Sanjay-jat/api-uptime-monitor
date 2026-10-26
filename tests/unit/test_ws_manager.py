import asyncio

from app import ws as ws_module
from app.ws import ConnectionManager


class FakeWS:
    def __init__(self, error=None, hang=False):
        self.sent = []
        self.error = error
        self.hang = hang

    async def send_json(self, payload):
        if self.hang:
            await asyncio.sleep(3600)
        if self.error:
            raise self.error
        self.sent.append(payload)


async def test_broadcast_reaches_all_sockets_of_user():
    m = ConnectionManager()
    a, b = FakeWS(), FakeWS()
    m.add(1, a)
    m.add(1, b)
    await m.broadcast(1, {"x": 1})
    assert a.sent == [{"x": 1}]
    assert b.sent == [{"x": 1}]


async def test_other_user_does_not_receive():
    m = ConnectionManager()
    mine, theirs = FakeWS(), FakeWS()
    m.add(1, mine)
    m.add(2, theirs)
    await m.broadcast(1, {"x": 1})
    assert mine.sent == [{"x": 1}]
    assert theirs.sent == []


async def test_broadcast_unknown_user_is_noop():
    await ConnectionManager().broadcast(99, {"x": 1})


async def test_disconnected_socket_gets_nothing():
    m = ConnectionManager()
    a, b = FakeWS(), FakeWS()
    m.add(1, a)
    m.add(1, b)
    m.disconnect(1, a)
    await m.broadcast(1, {"x": 1})
    assert a.sent == []
    assert b.sent == [{"x": 1}]


def test_disconnect_last_socket_drops_user_entry():
    m = ConnectionManager()
    a = FakeWS()
    m.add(1, a)
    m.disconnect(1, a)
    assert 1 not in m._conns


def test_double_disconnect_and_unknown_are_noop():
    m = ConnectionManager()
    a = FakeWS()
    m.add(1, a)
    m.add(1, FakeWS())
    m.disconnect(1, a)
    m.disconnect(1, a)  # dobara: crash nahi
    m.disconnect(99, a)  # anjaan user: crash nahi


async def test_dead_socket_removed_and_others_still_served():
    m = ConnectionManager()
    dead, ok = FakeWS(error=RuntimeError("closed")), FakeWS()
    m.add(1, dead)
    m.add(1, ok)
    await m.broadcast(1, {"x": 1})
    assert ok.sent == [{"x": 1}]
    assert dead not in m._conns[1]
    await m.broadcast(1, {"x": 2})
    assert ok.sent == [{"x": 1}, {"x": 2}]


async def test_slow_socket_times_out_and_is_removed(monkeypatch):
    monkeypatch.setattr(ws_module, "SEND_TIMEOUT", 0.05)
    m = ConnectionManager()
    slow, ok = FakeWS(hang=True), FakeWS()
    m.add(1, slow)
    m.add(1, ok)
    await m.broadcast(1, {"x": 1})
    assert ok.sent == [{"x": 1}]
    assert slow not in m._conns[1]


async def test_last_dead_socket_drops_user_entry():
    m = ConnectionManager()
    m.add(1, FakeWS(error=RuntimeError("closed")))
    await m.broadcast(1, {"x": 1})
    assert 1 not in m._conns
