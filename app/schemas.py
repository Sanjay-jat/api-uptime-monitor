from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.ssrf import _get_host


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return v.lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v.encode()) > 72:
            raise ValueError("Password must not be longer than 72 bytes")
        return v


class UserOut(BaseModel):
    id: int
    email: EmailStr
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str


class RefreshIn(BaseModel):
    refresh_token: str = Field(max_length=256)


MIN_INTERVAL = 60
MAX_INTERVAL = 86400


class EndpointCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(max_length=2048)
    method: Literal["GET", "HEAD"] = "GET"
    interval_seconds: int = Field(ge=MIN_INTERVAL, le=MAX_INTERVAL)
    timeout_seconds: int = Field(ge=1, le=30, default=10)
    expected_status: int = Field(ge=100, le=599, default=200)

    @field_validator("url")
    @classmethod
    def url_must_be_safe(cls, v: str) -> str:
        _get_host(v)
        return v


class EndpointUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str | None = Field(default=None, max_length=2048)
    method: Literal["GET", "HEAD"] | None = None
    interval_seconds: int | None = Field(default=None, ge=MIN_INTERVAL, le=MAX_INTERVAL)
    timeout_seconds: int | None = Field(default=None, ge=1, le=30)
    expected_status: int | None = Field(default=None, ge=100, le=599)
    is_active: bool | None = None

    @field_validator("url")
    @classmethod
    def url_must_be_safe(cls, v: str | None) -> str | None:
        if v is not None:
            _get_host(v)
        return v


class EndpointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    method: str
    interval_seconds: int
    timeout_seconds: int
    expected_status: int
    is_active: bool
    next_check_at: datetime
    created_at: datetime


class WebhookIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(max_length=2048)

    @field_validator("url")
    @classmethod
    def check_url(cls, v: str) -> str:
        _get_host(v)
        return v


class WebhookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    webhook_url: str
    webhook_secret: str


class PingOut(BaseModel):
    checked_at: datetime
    ok: bool
    status_code: int | None
    response_ms: int | None
    error: str | None
    model_config = ConfigDict(from_attributes=True)


class UptimeOut(BaseModel):
    window: Literal["24h", "7d", "30d"]
    uptime_percent: float | None
    total_checks: int


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    opened_at: datetime
    resolved_at: datetime | None
