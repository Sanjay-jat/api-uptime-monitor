import asyncio
from contextlib import suppress

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app import cache
from app.deps import DbSession
from app.models import User
from app.security import decode_access_token
from app.ws import manager

router = APIRouter(tags=["dashboard"])

AUTH_TIMEOUT = 10.0


async def _authenticate(ws: WebSocket, db) -> int | None:
    try:
        async with asyncio.timeout(AUTH_TIMEOUT):
            msg = await ws.receive_json()
        if not isinstance(msg, dict) or not isinstance(msg.get("token"), str):
            return None
        payload = decode_access_token(msg["token"])
        user = await db.get(User, int(payload["sub"]))
    except (TimeoutError, WebSocketDisconnect, jwt.InvalidTokenError, ValueError, KeyError):
        return None
    return user.id if user else None


# shortcut: no heartbeat, half-open socket stays until send fails; add ping later
@router.websocket("/ws/dashboard")
async def dashboard(ws: WebSocket, db: DbSession):
    await ws.accept()
    user_id = await _authenticate(ws, db)
    await db.close()
    if user_id is None:
        with suppress(RuntimeError):
            await ws.close(code=1008)
        return
    manager.add(user_id, ws)
    try:
        await ws.send_json({"type": "snapshot", "data": cache.get_user_statuses(user_id)})
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(user_id, ws)
