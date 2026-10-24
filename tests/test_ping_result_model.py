from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import Endpoint, PingResult, User


async def test_ping_result_saved_with_defaults(engine):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        user = User(email="a@example.com", password_hash="x")
        s.add(user)
        await s.flush()
        ep = Endpoint(user_id=user.id, url="https://a.example.com", interval_seconds=60)
        s.add(ep)
        await s.flush()
        s.add(PingResult(endpoint_id=ep.id, ok=False, error="timeout"))
        await s.commit()

    async with Session() as s:
        row = (await s.execute(select(PingResult))).scalar_one()

    assert row.checked_at is not None
    assert row.checked_at.tzinfo is not None
    assert row.ok is False
    assert row.status_code is None
    assert row.response_ms is None
    assert row.error == "timeout"


async def test_deleting_endpoint_cascades_only_its_pings(engine):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        user = User(email="b@example.com", password_hash="x")
        s.add(user)
        await s.flush()
        e1 = Endpoint(user_id=user.id, url="https://a.example.com", interval_seconds=60)
        e2 = Endpoint(user_id=user.id, url="https://b.example.com", interval_seconds=60)
        s.add_all([e1, e2])
        await s.flush()
        s.add_all(
            [
                PingResult(endpoint_id=e1.id, ok=True, status_code=200, response_ms=5),
                PingResult(endpoint_id=e1.id, ok=True),
                PingResult(endpoint_id=e2.id, ok=True),
            ]
        )
        await s.commit()
        e1_id, e2_id = e1.id, e2.id

    async with Session() as s:
        await s.execute(delete(Endpoint).where(Endpoint.id == e1_id))
        await s.commit()

    async with Session() as s:
        left = (await s.execute(select(PingResult.endpoint_id))).scalars().all()

    assert left == [e2_id]
