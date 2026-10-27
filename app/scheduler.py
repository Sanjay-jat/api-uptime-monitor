import asyncio
import contextlib
import logging
import random
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import cache
from app.alerts import build_body, send_webhook
from app.config import get_settings
from app.models import Endpoint, Incident, PingResult, User
from app.monitor import Event, Status, next_state, ping
from app.ws import manager

logger = logging.getLogger(__name__)


async def select_due(session: AsyncSession, now: datetime, limit: int = 100) -> list[Endpoint]:
    stmt = (
        select(Endpoint)
        .where(Endpoint.is_active, Endpoint.next_check_at <= now)
        .order_by(Endpoint.next_check_at)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def check_endpoint(
    session: AsyncSession,
    client: httpx.AsyncClient,
    ep: Endpoint,
    now: datetime,
    threshold: int = 3,
) -> Event:
    result = await ping(client, ep.url, ep.method, ep.timeout_seconds, ep.expected_status)
    state = next_state(ep.fail_count, Status(ep.status), result.ok, threshold)

    session.add(
        PingResult(
            endpoint_id=ep.id,
            checked_at=now,
            ok=result.ok,
            status_code=result.status_code,
            response_ms=result.response_ms,
            error=result.error,
        )
    )
    ep.fail_count = state.fail_count
    ep.status = state.status
    ep.next_check_at = now + timedelta(seconds=ep.interval_seconds * random.uniform(1.0, 1.1))
    event = state.event
    if event == Event.WENT_DOWN:
        session.add(Incident(endpoint_id=ep.id, opened_at=now))
    elif event == Event.RECOVERED:
        await session.execute(
            update(Incident)
            .where(Incident.endpoint_id == ep.id, Incident.resolved_at.is_(None))
            .values(resolved_at=now)
        )
    user_id = ep.user_id
    payload = {
        "endpoint_id": ep.id,
        "status": state.status.value,
        "ok": result.ok,
        "status_code": result.status_code,
        "response_ms": result.response_ms,
        "checked_at": now.isoformat(),
    }
    await session.commit()
    cache.set_status(user_id, ep.id, payload)
    await manager.broadcast(user_id, {"type": "update", "data": payload})
    return state.event


async def _check_one(
    session_factory: async_sessionmaker[AsyncSession],
    client: httpx.AsyncClient,
    ep_id: int,
    now: datetime,
    threshold: int,
    sem: asyncio.Semaphore,
) -> None:
    async with sem:
        try:
            async with session_factory() as session:
                ep = await session.get(Endpoint, ep_id)
                if ep is None or not ep.is_active:
                    return
                event = await check_endpoint(session, client, ep, now, threshold)
                await _alert(session, client, ep, event, now)
        except Exception:
            logger.exception("check failed for endpoint %s", ep_id)


async def run_tick(
    session_factory: async_sessionmaker[AsyncSession],
    client: httpx.AsyncClient,
    now: datetime,
    threshold: int = 3,
    max_concurrency: int = 10,
) -> None:
    async with session_factory() as session:
        due = await select_due(session, now)
    sem = asyncio.Semaphore(max_concurrency)
    await asyncio.gather(
        *(_check_one(session_factory, client, e.id, now, threshold, sem) for e in due)
    )


PURGE_EVERY = timedelta(hours=24)


async def run_purge(session_factory, now: datetime, days: int) -> int:
    async with session_factory() as s:
        return await purge_old_pings(s, now, days)


async def run_scheduler(
    session_factory: async_sessionmaker[AsyncSession],
    client: httpx.AsyncClient,
    stop: asyncio.Event,
    tick_seconds: float = 1.0,
    threshold: int = 3,
) -> None:
    last_purge = datetime.min.replace(tzinfo=UTC)
    while not stop.is_set():
        now = datetime.now(UTC)
        try:
            await run_tick(session_factory, client, now, threshold)
        except Exception:
            logger.exception("tick failed")
        if now - last_purge >= PURGE_EVERY:
            try:
                await run_purge(session_factory, now, get_settings().retention_days)
            except Exception:
                logger.exception("purge failed")
            last_purge = now
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)


async def _alert(
    session: AsyncSession,
    client: httpx.AsyncClient,
    ep: Endpoint,
    event: Event,
    now: datetime,
) -> None:
    if event not in (Event.WENT_DOWN, Event.RECOVERED):
        return
    user = await session.get(User, ep.user_id)
    if user is None or not user.webhook_url or not user.webhook_secret:
        return
    body = build_body(event, ep.id, ep.url, now)
    await send_webhook(client, user.webhook_url, user.webhook_secret, body)


async def purge_old_pings(session, now: datetime, days: int, batch: int = 1000) -> int:
    cutoff = now - timedelta(days=days)
    total = 0
    while True:
        ids = select(PingResult.id).where(PingResult.checked_at < cutoff).limit(batch)
        result = await session.execute(delete(PingResult).where(PingResult.id.in_(ids)))
        await session.commit()
        total += result.rowcount
        if result.rowcount < batch:
            break
    return total
