from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import Endpoint, User
from app.monitor import Event
from app.scheduler import _alert

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


async def test_no_open_transaction_while_sending_webhook(engine, monkeypatch):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        seen = []

        async def _send(*args, **kwargs):
            seen.append(s.in_transaction())
            return True

        monkeypatch.setattr("app.scheduler.send_webhook", _send)
        user = User(
            email="a@example.com",
            password_hash="x",
            webhook_url="https://hook.example.com/h",
            webhook_secret="secret",
        )
        s.add(user)
        await s.flush()
        ep = Endpoint(
            user_id=user.id, url="https://a.example.com", interval_seconds=60, next_check_at=NOW
        )
        s.add(ep)
        await s.commit()
        await _alert(s, None, ep, Event.WENT_DOWN, NOW)

    assert seen == [False]
