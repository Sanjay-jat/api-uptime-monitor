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


def test_jwt_settings_loaded():
    settings = get_settings()
    assert len(settings.jwt_secret) >= 32
    assert settings.jwt_algorithm == "HS256"


def test_token_lifetimes_positive():
    settings = get_settings()
    assert settings.access_token_minutes > 0
    assert settings.refresh_token_days > 0
