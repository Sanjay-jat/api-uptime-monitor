import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.db import SessionLocal, engine
from app.routers import auth, dashboard, endpoints, history
from app.scheduler import run_scheduler

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
app.include_router(auth.router)
app.include_router(endpoints.router)
app.include_router(history.router)
app.include_router(dashboard.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
