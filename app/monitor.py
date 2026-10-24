import asyncio
import logging
import time
from enum import StrEnum
from typing import NamedTuple

import httpx

from app.ssrf import UnsafeURLError, validate_public_url

logger = logging.getLogger(__name__)


class Status(StrEnum):
    UP = "up"
    DOWN = "down"


class Event(StrEnum):
    NONE = "none"
    WENT_DOWN = "went_down"
    RECOVERED = "recovered"


class State(NamedTuple):
    fail_count: int
    status: Status
    event: Event


class CheckResult(NamedTuple):
    ok: bool
    status_code: int | None
    response_ms: int | None
    error: str | None


def _fail(error: str) -> CheckResult:
    return CheckResult(ok=False, status_code=None, response_ms=None, error=error)


def next_state(prev_fail_count: int, status: Status, ok: bool, threshold: int) -> State:
    if threshold < 1:
        raise ValueError("threshold must be >= 1")
    if ok:
        fail_count = 0
        if status == Status.DOWN:
            return State(fail_count=fail_count, status=Status.UP, event=Event.RECOVERED)
        else:
            return State(fail_count=fail_count, status=Status.UP, event=Event.NONE)
    fail_count = prev_fail_count + 1
    if status == Status.UP and fail_count >= threshold:
        return State(fail_count=fail_count, status=Status.DOWN, event=Event.WENT_DOWN)
    else:
        return State(fail_count=fail_count, status=status, event=Event.NONE)


async def ping(
    client: httpx.AsyncClient,
    url: str,
    method: str,
    timeout: float,
    expected_status: int,
) -> CheckResult:
    start = time.perf_counter()
    try:
        async with asyncio.timeout(timeout):
            await validate_public_url(url)
            async with client.stream(method, url) as response:
                status_code = response.status_code
    except UnsafeURLError:
        return _fail("blocked_url")
    except (TimeoutError, httpx.TimeoutException):
        return _fail("timeout")
    except httpx.HTTPError:
        return _fail("connection_error")
    except Exception:
        logger.exception("ping failed")
        return _fail("internal_error")
    ms = int((time.perf_counter() - start) * 1000)
    ok = status_code == expected_status
    return CheckResult(
        ok=ok,
        status_code=status_code,
        response_ms=ms,
        error=None if ok else "unexpected_status",
    )
