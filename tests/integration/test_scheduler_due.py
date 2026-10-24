from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import Endpoint, User
from app.scheduler import select_due

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _ep(user_id: int, name: str, next_check_at: datetime, is_active: bool = True) -> Endpoint:
    return Endpoint(
        user_id=user_id,
        url=f"https://{name}.example.com",
        interval_seconds=60,
        next_check_at=next_check_at,
        is_active=is_active,
    )


async def _seed(engine, endpoints_fn):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        user = User(email="a@example.com", password_hash="x")
        s.add(user)
        await s.flush()
        s.add_all(endpoints_fn(user.id))
        await s.commit()
    return Session


async def test_returns_only_due_active_endpoints(engine):
    Session = await _seed(
        engine,
        lambda uid: [
            _ep(uid, "past", NOW - timedelta(seconds=1)),
            _ep(uid, "exact", NOW),
            _ep(uid, "future", NOW + timedelta(seconds=1)),
            _ep(uid, "paused", NOW - timedelta(hours=1), is_active=False),
        ],
    )
    async with Session() as s:
        due = await select_due(s, NOW)

    assert [e.url for e in due] == [
        "https://past.example.com",
        "https://exact.example.com",
    ]


async def test_most_overdue_first(engine):
    Session = await _seed(
        engine,
        lambda uid: [
            _ep(uid, "recent", NOW - timedelta(seconds=5)),
            _ep(uid, "oldest", NOW - timedelta(hours=1)),
            _ep(uid, "middle", NOW - timedelta(minutes=1)),
        ],
    )
    async with Session() as s:
        due = await select_due(s, NOW)

    assert [e.url for e in due] == [
        "https://oldest.example.com",
        "https://middle.example.com",
        "https://recent.example.com",
    ]


async def test_limit_is_respected(engine):
    Session = await _seed(
        engine,
        lambda uid: [_ep(uid, f"e{i}", NOW - timedelta(minutes=i + 1)) for i in range(3)],
    )
    async with Session() as s:
        due = await select_due(s, NOW, limit=2)

    assert [e.url for e in due] == [
        "https://e2.example.com",
        "https://e1.example.com",
    ]


async def test_nothing_due_returns_empty_list(engine):
    Session = await _seed(engine, lambda uid: [_ep(uid, "later", NOW + timedelta(hours=1))])
    async with Session() as s:
        assert await select_due(s, NOW) == []
