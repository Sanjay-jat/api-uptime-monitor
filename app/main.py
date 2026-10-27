import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.db import SessionLocal, engine
from app.errors import rate_limit_handler, validation_handler
from app.limits import limiter
from app.middleware import request_context
from app.routers import auth, dashboard, endpoints, history
from app.scheduler import run_scheduler

logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    client = httpx.AsyncClient(follow_redirects=False, timeout=None)
    stops = asyncio.Event()
    task = asyncio.create_task(run_scheduler(SessionLocal, client, stops))
    try:
        yield
    finally:
        stops.set()
        try:
            await asyncio.wait_for(task, timeout=10)
        except asyncio.TimeoutError:
            logger.warning("scheduler did not stop in time")
        await client.aclose()
        await engine.dispose()


app = FastAPI(lifespan=lifespan)
app.middleware("http")(request_context)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Request-ID"],
)
app.include_router(auth.router)
app.include_router(endpoints.router)
app.include_router(history.router)
app.include_router(dashboard.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


app.state.limiter = limiter
app.add_exception_handler(RequestValidationError, validation_handler)
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
