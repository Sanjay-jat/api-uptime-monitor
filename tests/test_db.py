from sqlalchemy import text

from app.db import engine


async def test_db_connects():
    async with engine.connect() as conn:
        assert await conn.scalar(text("select 1")) == 1
