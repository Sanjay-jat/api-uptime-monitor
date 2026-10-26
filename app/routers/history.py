from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.deps import CurrentUser, DbSession
from app.models import Incident, PingResult
from app.routers.endpoints import _get_owned
from app.schemas import IncidentOut, PingOut, UptimeOut

router = APIRouter(prefix="/endpoints", tags=["history"])


@router.get("/{endpoint_id}/pings", response_model=list[PingOut])
async def list_pings(
    endpoint_id: int,
    user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    await _get_owned(db, user.id, endpoint_id)  # 404 agar nahi mila
    stmt = (
        select(PingResult)
        .where(PingResult.endpoint_id == endpoint_id)
        .order_by(PingResult.checked_at.desc(), PingResult.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return (await db.scalars(stmt)).all()


WINDOWS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


def uptime_percent(ok: int, total: int) -> float | None:
    if total == 0:
        return None
    return round(ok / total * 100, 2)


@router.get("/{endpoint_id}/uptime", response_model=UptimeOut)
async def get_uptime(
    endpoint_id: int,
    user: CurrentUser,
    db: DbSession,
    window: Literal["24h", "7d", "30d"] = "24h",
):
    await _get_owned(db, user.id, endpoint_id)
    cutoff = datetime.now(UTC) - WINDOWS[window]
    stmt = select(func.count(), func.count().filter(PingResult.ok)).where(
        PingResult.endpoint_id == endpoint_id,
        PingResult.checked_at >= cutoff,
    )
    total, ok = (await db.execute(stmt)).one()
    return UptimeOut(window=window, uptime_percent=uptime_percent(ok, total), total_checks=total)


@router.get("/{endpoint_id}/incidents", response_model=list[IncidentOut])
async def list_incidents(
    endpoint_id: int,
    user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    await _get_owned(db, user.id, endpoint_id)  # 404 agar nahi mila
    stmt = (
        select(Incident)
        .where(Incident.endpoint_id == endpoint_id)
        .order_by(Incident.opened_at.desc(), Incident.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return (await db.scalars(stmt)).all()
