from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import init_db
from .routers.analytics import router as analytics_router
from .routers.imports import router as imports_router
from .routers.site import router as site_router, site_root


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    yield


app = FastAPI(
    title="Budget Analytics Import API",
    version="0.1.0",
    description="API for importing budget CSV datasets from folders and archives.",
    lifespan=lifespan,
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


app.mount("/static", StaticFiles(directory=site_root()), name="static")
app.include_router(site_router)
app.include_router(imports_router)
app.include_router(analytics_router)
