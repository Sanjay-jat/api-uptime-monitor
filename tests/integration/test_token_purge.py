from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import RefreshToken, User
from app.scheduler import purge_expired_tokens, run_purge

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


async def _seed(Session, rows):
    async with Session() as s:
        user = User(email="a@example.com", password_hash="x")
        s.add(user)
        await s.flush()
        s.add_all(
            RefreshToken(user_id=user.id, token_hash=h, expires_at=exp, revoked_at=rev)
            for h, exp, rev in rows
        )
        await s.commit()


async def _hashes(Session) -> list[str]:
    async with Session() as s:
        return list(
            (
                await s.scalars(select(RefreshToken.token_hash).order_by(RefreshToken.token_hash))
            ).all()
        )


async def test_purge_removes_only_expired_tokens(engine):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    future = NOW + timedelta(days=1)
    await _seed(
        Session,
        [
            ("a" * 64, NOW - timedelta(seconds=1), None),
            ("b" * 64, future, None),
            ("c" * 64, future, NOW),
        ],
    )
    async with Session() as s:
        removed = await purge_expired_tokens(s, NOW)
    assert removed == 1
    assert await _hashes(Session) == ["b" * 64, "c" * 64]


async def test_run_purge_also_cleans_expired_tokens(engine):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    await _seed(Session, [("a" * 64, NOW - timedelta(days=1), None)])
    await run_purge(Session, NOW, 30)
    assert await _hashes(Session) == []
