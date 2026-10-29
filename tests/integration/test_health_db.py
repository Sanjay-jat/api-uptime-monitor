from app.db import get_db
from app.main import app


async def test_health_is_503_when_db_is_down(client, monkeypatch):
    class BrokenSession:
        async def execute(self, *args, **kwargs):
            raise RuntimeError("db down")

    async def broken_get_db():
        yield BrokenSession()

    monkeypatch.setitem(app.dependency_overrides, get_db, broken_get_db)
    r = await client.get("/health")
    assert r.status_code == 503
    assert r.json() == {"detail": "Database unavailable"}
