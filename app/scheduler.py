import random
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Endpoint, PingResult
from app.monitor import Event, Status, next_state, ping


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
