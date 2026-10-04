import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def get_clear_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_database_url():
    assert get_settings().database_url.startswith("postgresql+asyncpg://")


def test_env_var_overrides_dotenv(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x")
    assert get_settings().database_url == "postgresql+asyncpg://x"
