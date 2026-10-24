from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Endpoint


async def select_due(session: AsyncSession, now: datetime, limit: int = 100) -> list[Endpoint]:
    stmt = (
        select(Endpoint)
        .where(Endpoint.is_active, Endpoint.next_check_at <= now)
        .order_by(Endpoint.next_check_at)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
