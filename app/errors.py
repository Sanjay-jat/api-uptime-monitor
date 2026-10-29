from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded


async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    detail = [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": detail})


# shortcut: all limits are per minute; read the window from the limit if that changes
RETRY_AFTER_SECONDS = "60"


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded"},
        headers={"Retry-After": RETRY_AFTER_SECONDS},
    )
