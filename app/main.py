from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routers import auth, endpoints


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(auth.router)
app.include_router(endpoints.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
