from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import cache
from app.config import get_settings
from app.deps import CurrentUser, DbSession
from app.limits import limiter, user_key
from app.models import Endpoint, User
from app.schemas import EndpointCreate, EndpointOut, EndpointUpdate
from app.ssrf import UnsafeURLError, validate_public_url

router = APIRouter(prefix="/endpoints", tags=["endpoints"])
CREATE_LIMIT = "10/minute"
UPDATE_LIMIT = "10/minute"


async def _get_owned(db: AsyncSession, user_id: int, endpoint_id: int) -> Endpoint:
    result = await db.execute(
        select(Endpoint).where(Endpoint.id == endpoint_id, Endpoint.user_id == user_id)
    )
    ep = result.scalar_one_or_none()
    if ep is None:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    return ep


@router.post("", response_model=EndpointOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(CREATE_LIMIT, key_func=user_key)
async def create_endpoint(request: Request, body: EndpointCreate, db: DbSession, user: CurrentUser):
    try:
        await validate_public_url(body.url)
    except UnsafeURLError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    count = await db.scalar(
        select(func.count()).select_from(Endpoint).where(Endpoint.user_id == user.id)
    )
    limit = get_settings().max_endpoints_per_user
    if count >= limit:
        raise HTTPException(
            status_code=403, detail=f"User has reached the maximum number of endpoints ({limit})"
        )
    ep = Endpoint(user_id=user.id, **body.model_dump(exclude_none=True))
    db.add(ep)
    await db.commit()
    await db.refresh(ep)
    return ep


@router.get("", response_model=list[EndpointOut])
async def list_endpoints(db: DbSession, user: CurrentUser):
    result = await db.execute(
        select(Endpoint).where(Endpoint.user_id == user.id).order_by(Endpoint.id)
    )
    return result.scalars().all()


@router.get("/{endpoint_id}", response_model=EndpointOut)
async def get_endpoint(endpoint_id: int, db: DbSession, user: CurrentUser):
    return await _get_owned(db, user.id, endpoint_id)


@router.patch("/{endpoint_id}", response_model=EndpointOut)
@limiter.limit(UPDATE_LIMIT, key_func=user_key)
async def update_endpoint(
    request: Request, body: EndpointUpdate, db: DbSession, user: CurrentUser, endpoint_id: int
):
    ep = await _get_owned(db, user.id, endpoint_id)
    if body.url is not None:
        try:
            await validate_public_url(body.url)
        except UnsafeURLError as e:
            raise HTTPException(status_code=422, detail=str(e)) from None
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(ep, key, value)
    if body.interval_seconds is not None:
        due = datetime.now(UTC) + timedelta(seconds=ep.interval_seconds)
        ep.next_check_at = min(ep.next_check_at, due)
    await db.commit()
    await db.refresh(ep)
    return ep


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_endpoint(endpoint_id: int, db: DbSession, user: CurrentUser):
    ep = await _get_owned(db, user.id, endpoint_id)
    await db.delete(ep)
    await db.commit()
    cache.remove(user.id, endpoint_id)
