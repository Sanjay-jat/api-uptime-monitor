import asyncio
import socket

import httpx
import pytest
import respx

from app.main import app, lifespan
from app.monitor import ping


@pytest.fixture()
def seen(monkeypatch):
    info: dict = {}

    async def _run(session_factory, client, stop, *args, **kwargs):
        info["client"] = client
        info["stop"] = stop
        await stop.wait()
        info["finished"] = True

    monkeypatch.setattr("app.main.run_scheduler", _run)
    return info


@pytest.fixture()
def public_dns(monkeypatch):
    def _getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _getaddrinfo)


async def test_lifespan_starts_and_stops_scheduler(seen):
    async with lifespan(app):
        await asyncio.sleep(0)
        assert "client" in seen
        assert not seen["stop"].is_set()
        assert "finished" not in seen

    assert seen["stop"].is_set()
    assert seen["finished"] is True
    assert seen["client"].is_closed


async def test_scheduler_stopped_even_if_app_errors(seen):
    with pytest.raises(RuntimeError):
        async with lifespan(app):
            await asyncio.sleep(0)
            raise RuntimeError("boom")

    assert seen["finished"] is True
    assert seen["client"].is_closed


async def test_scheduler_client_does_not_follow_redirects(seen, public_dns):
    async with lifespan(app):
        await asyncio.sleep(0)
        client = seen["client"]
        with respx.mock:
            respx.get("https://a.example.com").mock(
                return_value=httpx.Response(302, headers={"Location": "http://169.254.169.254/"})
            )
            metadata = respx.get("http://169.254.169.254/").mock(return_value=httpx.Response(200))
            result = await ping(client, "https://a.example.com", "GET", 5, 200)

    assert result.ok is False
    assert metadata.called is False


async def test_scheduler_client_has_no_httpx_timeout(seen):
    async with lifespan(app):
        await asyncio.sleep(0)
        assert seen["client"].timeout == httpx.Timeout(None)
