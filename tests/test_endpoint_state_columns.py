from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import Endpoint, User


async def test_orm_endpoint_starts_up_with_zero_fails(engine):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        user = User(email="a@example.com", password_hash="x")
        s.add(user)
        await s.flush()
        s.add(Endpoint(user_id=user.id, url="https://a.example.com", interval_seconds=60))
        await s.commit()

    async with Session() as s:
        ep = (await s.execute(select(Endpoint))).scalar_one()

    assert ep.fail_count == 0
    assert ep.status == "up"


async def test_raw_sql_insert_gets_db_defaults(engine):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        user = User(email="b@example.com", password_hash="x")
        s.add(user)
        await s.flush()
        await s.execute(
            text(
                "INSERT INTO endpoints "
                "(user_id, url, method, interval_seconds, timeout_seconds, expected_status) "
                "VALUES (:uid, 'https://b.example.com', 'GET', 60, 10, 200)"
            ),
            {"uid": user.id},
        )
        await s.commit()

    async with Session() as s:
        ep = (await s.execute(select(Endpoint))).scalar_one()

    assert ep.fail_count == 0
    assert ep.status == "up"
