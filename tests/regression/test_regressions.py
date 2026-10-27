import logging

import httpx
import respx

from app import main  # noqa: F401  (import sets the httpx log level)


@respx.mock
async def test_httpx_does_not_log_url_with_secret_query(caplog):
    """httpx INFO log used to print full monitored URL, leaking ?token=..."""
    respx.get("https://example.com/").respond(200)
    caplog.set_level(logging.INFO)
    async with httpx.AsyncClient() as c:
        await c.get("https://example.com/?token=SECRET")
    assert "SECRET" not in caplog.text
