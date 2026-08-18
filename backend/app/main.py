"""MONITOR Web CRM API."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from app.config import get_settings
from app.crm.delay_scheduler import analise_reset_loop, delayed_tasks_restore_loop
from app.db import close_pool, init_pool
from app.monitor.app_metrics import RequestMetricsMiddleware
from app.routes import (
    auth,
    employee_locations,
    excel_uploads,
    field_score,
    layers,
    letters,
    monitor,
    order_tracks,
    ozn_match,
    personnel,
    photos,
    tasks,
    zip_close,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_pool()
    stop = asyncio.Event()
    restore_task = asyncio.create_task(delayed_tasks_restore_loop(stop))
    analise_task = asyncio.create_task(analise_reset_loop(stop))
    try:
        yield
    finally:
        stop.set()
        for task in (restore_task, analise_task):
            try:
                await asyncio.wait_for(task, timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        close_pool()


app = FastAPI(
    title="MONITOR Web CRM",
    version="1.0.0",
    description="Web CRM with Leaflet map for Monitor PostGIS database.",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(RequestMetricsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(excel_uploads.router)
app.include_router(layers.router)
app.include_router(tasks.router)
app.include_router(letters.router)
app.include_router(order_tracks.router)
app.include_router(ozn_match.router)
app.include_router(employee_locations.router)
app.include_router(field_score.router)
app.include_router(photos.router)
app.include_router(personnel.router)
app.include_router(monitor.router)
app.include_router(zip_close.router)


@app.middleware("http")
async def no_store_api_cache(request: Request, call_next) -> Response:
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
