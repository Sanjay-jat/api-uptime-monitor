from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    test_database_url: str
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    max_endpoints_per_user: int = 10
    cors_origins: list[str] = []
    retention_days: int = 30


@lru_cache
def get_settings() -> Settings:
    """Creates and caches a single instance of the Settings object."""
    return Settings()
