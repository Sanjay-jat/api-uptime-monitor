import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings


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


def test_test_database_url_is_optional(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    assert Settings(_env_file=None).test_database_url is None


def test_short_jwt_secret_is_rejected(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x")
    monkeypatch.setenv("JWT_SECRET", "x" * 31)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_32_char_jwt_secret_is_accepted(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    assert len(Settings(_env_file=None).jwt_secret) == 32


def test_env_example_secret_is_not_usable(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=".env.example")
    assert "jwt_secret" in str(exc.value)
