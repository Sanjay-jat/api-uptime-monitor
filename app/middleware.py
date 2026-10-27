import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

logger = logging.getLogger("app.access")


async def request_context(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    rid = str(uuid.uuid4())
    request.state.request_id = rid
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("unhandled request_id=%s", rid)
        response = JSONResponse(
            status_code=500, content={"detail": "Internal server error", "request_id": rid}
        )
    response.headers["X-Request-ID"] = rid
    logger.info(
        json.dumps(
            {
                "event": "request",
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                "request_id": rid,
            }
        )
    )
    return response
