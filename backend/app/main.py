"""MONITOR Web CRM API."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import close_pool, init_pool
from app.routes import auth, employee_locations, layers, order_tracks, personnel, photos, tasks


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_pool()
    yield
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
app.include_router(order_tracks.router)
app.include_router(employee_locations.router)
app.include_router(photos.router)
app.include_router(personnel.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
