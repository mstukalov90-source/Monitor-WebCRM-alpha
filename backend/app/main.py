"""MONITOR Web CRM API."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.crm.delay_scheduler import delayed_tasks_restore_loop
from app.db import close_pool, init_pool
from app.routes import (
    auth,
    employee_locations,
    field_score,
    layers,
    letters,
    order_tracks,
    personnel,
    photos,
    tasks,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_pool()
    stop = asyncio.Event()
    restore_task = asyncio.create_task(delayed_tasks_restore_loop(stop))
    try:
        yield
    finally:
        stop.set()
        try:
            await asyncio.wait_for(restore_task, timeout=5)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            restore_task.cancel()
            try:
                await restore_task
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(layers.router)
app.include_router(tasks.router)
app.include_router(letters.router)
app.include_router(order_tracks.router)
app.include_router(employee_locations.router)
app.include_router(field_score.router)
app.include_router(photos.router)
app.include_router(personnel.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
