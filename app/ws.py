import asyncio
import contextlib
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

SEND_TIMEOUT = 5.0
CLOSE_TIMEOUT = 2.0


# shortcut: sequential send, slow client max 5s; 1 worker, multi-worker ke liye Redis pub/sub
class ConnectionManager:
    def __init__(self) -> None:
        self._conns: dict[int, set[WebSocket]] = {}

    def add(self, user_id: int, ws: WebSocket) -> None:
        self._conns.setdefault(user_id, set()).add(ws)

    def disconnect(self, user_id: int, ws: WebSocket) -> None:
        sockets = self._conns.get(user_id)
        if sockets is None:
            return
        sockets.discard(ws)
        if not sockets:
            del self._conns[user_id]

    async def _close(self, ws: WebSocket) -> None:
        # best effort: client sees the close and reconnects
        with contextlib.suppress(Exception):
            async with asyncio.timeout(CLOSE_TIMEOUT):
                await ws.close(code=1011)

    async def broadcast(self, user_id: int, payload: dict[str, Any]) -> None:
        for ws in list(self._conns.get(user_id, [])):
            try:
                async with asyncio.timeout(SEND_TIMEOUT):
                    await ws.send_json(payload)
            except Exception as exc:
                logger.warning("ws send failed: %s", type(exc).__name__)
                self.disconnect(user_id, ws)
                await self._close(ws)


manager = ConnectionManager()
