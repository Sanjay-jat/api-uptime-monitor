import hmac
import socket
from datetime import UTC, datetime

import httpx
import pytest

from app import alerts
from app.alerts import build_body, send_webhook, sign
from app.monitor import Event

URL = "https://hook.example.com/path-token-123"
SECRET = "topsecret"
BODY = build_body(Event.WENT_DOWN, 1, "https://a.example.com", datetime(2026, 1, 1, tzinfo=UTC))


@pytest.fixture
def dns(monkeypatch):
    table = {"hook.example.com": "93.184.216.34"}
    real = socket.getaddrinfo

    def fake(host, *args, **kwargs):
        if host in table:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (table[host], 0))]
        return real(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake)
    return table


@pytest.fixture
async def http():
    async with httpx.AsyncClient(follow_redirects=False, timeout=None) as c:
        yield c


async def test_success_sends_exact_body_and_valid_signature(http, dns, respx_mock):
    route = respx_mock.post(URL).respond(200)
    assert await send_webhook(http, URL, SECRET, BODY) is True
    req = route.calls.last.request
    assert req.content == BODY
    assert req.headers["content-type"] == "application/json"
    sig = req.headers["x-signature"]
    assert sig.startswith("sha256=")
    assert hmac.compare_digest(sig, "sha256=" + sign(SECRET, BODY))


async def test_non_2xx_is_false(http, dns, respx_mock):
    respx_mock.post(URL).respond(500)
    assert await send_webhook(http, URL, SECRET, BODY) is False


async def test_connect_error_is_false(http, dns, respx_mock):
    respx_mock.post(URL).mock(side_effect=httpx.ConnectError("boom"))
    assert await send_webhook(http, URL, SECRET, BODY) is False


async def test_unexpected_error_is_false_not_raised(http, dns, respx_mock):
    respx_mock.post(URL).mock(side_effect=RuntimeError("weird"))
    assert await send_webhook(http, URL, SECRET, BODY) is False


async def test_slow_receiver_times_out(http, dns, respx_mock, monkeypatch):
    import asyncio

    async def slow(request):
        await asyncio.sleep(1)
        return httpx.Response(200)

    monkeypatch.setattr(alerts, "SEND_TIMEOUT", 0.05)
    respx_mock.post(URL).mock(side_effect=slow)
    assert await send_webhook(http, URL, SECRET, BODY) is False


async def test_redirect_not_followed(http, dns, respx_mock):
    respx_mock.post(URL).respond(302, headers={"location": "http://169.254.169.254/x"})
    assert await send_webhook(http, URL, SECRET, BODY) is False


@pytest.mark.respx(assert_all_called=False)
async def test_private_ip_literal_blocked_no_request(http, respx_mock):
    route = respx_mock.post("http://127.0.0.1/hook").respond(200)
    assert await send_webhook(http, "http://127.0.0.1/hook", SECRET, BODY) is False
    assert route.called is False


@pytest.mark.respx(assert_all_called=False)
async def test_dns_now_private_blocked_no_request(http, dns, respx_mock):
    dns["hook.example.com"] = "10.0.0.5"  # save ke baad DNS badal gaya
    route = respx_mock.post(URL).respond(200)
    assert await send_webhook(http, URL, SECRET, BODY) is False
    assert route.called is False


async def test_failure_logs_do_not_leak_secret_or_url(http, dns, respx_mock, caplog):
    respx_mock.post(URL).mock(side_effect=httpx.ConnectError("boom"))
    await send_webhook(http, URL, SECRET, BODY)
    assert caplog.records
    assert SECRET not in caplog.text
    assert "path-token-123" not in caplog.text
