import asyncio
import hashlib
import hmac
import json
import logging
from datetime import datetime

import httpx

from app.monitor import Event
from app.ssrf import UnsafeURLError, validate_public_url

logger = logging.getLogger(__name__)

SEND_TIMEOUT = 10.0


def build_body(event: Event, endpoint_id: int, url: str, now: datetime) -> bytes:
    payload = {"event": event.value, "endpoint_id": endpoint_id, "url": url, "at": now.isoformat()}
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def send_webhook(client: httpx.AsyncClient, url: str, secret: str, body: bytes) -> bool:
    try:
        await validate_public_url(url)
    except UnsafeURLError:
        logger.warning("webhook blocked: unsafe url")
        return False
    headers = {"Content-Type": "application/json", "X-Signature": f"sha256={sign(secret, body)}"}
    try:
        async with asyncio.timeout(SEND_TIMEOUT):
            r = await client.post(url, content=body, headers=headers)
    except Exception as e:
        logger.warning("webhook failed: %s", type(e).__name__)
        return False
    if not r.is_success:
        logger.warning("webhook rejected: status %s", r.status_code)
    return r.is_success
