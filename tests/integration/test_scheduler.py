import asyncio
import socket

import httpx
import pytest

from app.monitor import ping

URL = "https://example.com/"


def _fake_dns(monkeypatch, ip):
    def fake(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake)


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    _fake_dns(monkeypatch, "93.184.216.34")


@pytest.fixture
async def http():
    async with httpx.AsyncClient(follow_redirects=False) as c:
        yield c


async def _ping(http, *, method="GET", timeout=5.0, expected=200):
    return await ping(http, URL, method, timeout, expected)


async def test_ping_200_is_up(http, respx_mock):
    respx_mock.get(URL).respond(200)
    r = await _ping(http)
    assert r.ok is True
    assert r.status_code == 200
    assert r.response_ms is not None
    assert r.error is None


async def test_ping_500_is_down(http, respx_mock):
    respx_mock.get(URL).respond(500)
    r = await _ping(http)
    assert r.ok is False
    assert r.status_code == 500
    assert r.error == "unexpected_status"


async def test_ping_custom_expected_status(http, respx_mock):
    respx_mock.get(URL).respond(204)
    r = await _ping(http, expected=204)
    assert r.ok is True


async def test_ping_head_method(http, respx_mock):
    route = respx_mock.head(URL).respond(200)
    r = await _ping(http, method="HEAD")
    assert r.ok is True
    assert route.called


async def test_ping_connect_timeout(http, respx_mock):
    respx_mock.get(URL).mock(side_effect=httpx.ConnectTimeout("x"))
    r = await _ping(http)
    assert r.ok is False
    assert r.status_code is None
    assert r.error == "timeout"


async def test_ping_total_deadline(http, respx_mock):
    async def slow(request):
        await asyncio.sleep(1)
        return httpx.Response(200)

    respx_mock.get(URL).mock(side_effect=slow)
    r = await _ping(http, timeout=0.05)
    assert r.ok is False
    assert r.error == "timeout"


async def test_ping_connection_error(http, respx_mock):
    respx_mock.get(URL).mock(side_effect=httpx.ConnectError("secret detail"))
    r = await _ping(http)
    assert r.ok is False
    assert r.error == "connection_error"
    assert "secret" not in r.error


async def test_ping_unexpected_exception_is_contained(http, respx_mock):
    respx_mock.get(URL).mock(side_effect=RuntimeError("secret detail"))
    r = await _ping(http)
    assert r.ok is False
    assert r.error == "internal_error"


@pytest.mark.respx(assert_all_called=False)
async def test_ping_redirect_not_followed(http, respx_mock):
    respx_mock.get(URL).respond(302, headers={"location": "http://169.254.169.254/"})
    meta = respx_mock.get("http://169.254.169.254/").respond(200)
    r = await _ping(http)
    assert r.ok is False
    assert r.status_code == 302
    assert r.error == "unexpected_status"
    assert not meta.called


@pytest.mark.respx(assert_all_called=False)
async def test_ping_private_ip_blocked_before_request(http, respx_mock, monkeypatch):
    _fake_dns(monkeypatch, "10.0.0.5")
    route = respx_mock.get(URL).respond(200)
    r = await _ping(http)
    assert r.ok is False
    assert r.error == "blocked_url"
    assert not route.called
