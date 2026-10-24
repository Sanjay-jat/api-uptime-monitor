import asyncio
import logging
import random
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Endpoint, PingResult
from app.monitor import Event, Status, next_state, ping

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
    await session.commit()
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
                await check_endpoint(session, client, ep, now, threshold)
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
