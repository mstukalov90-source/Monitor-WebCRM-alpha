"""Admin-only live server monitor."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth.deps import require_admin
from app.auth.session import UserSession
from app.monitor.snapshot import get_snapshot

router = APIRouter(prefix="/api/monitor", tags=["monitor"])


class MonitorDiskOut(BaseModel):
    path: str
    label: str
    used_bytes: int
    total_bytes: int
    percent: float


class MonitorHostOut(BaseModel):
    cpu_percent: float
    loadavg: list[float] | None = None
    memory_used_bytes: int
    memory_total_bytes: int
    memory_percent: float
    disks: list[MonitorDiskOut] = Field(default_factory=list)


class MonitorSlowQueryOut(BaseModel):
    pid: int
    duration_seconds: float
    query: str


class MonitorDatabaseOut(BaseModel):
    connections: int
    max_connections: int | None = None
    active_queries: int
    cache_hit_percent: float | None = None
    size_bytes: int
    slow_queries: list[MonitorSlowQueryOut] = Field(default_factory=list)


class MonitorAppOut(BaseModel):
    status: str
    rss_bytes: int | None = None
    cpu_percent: float | None = None
    pool_in_use: int
    pool_max: int
    requests_per_minute: int
    p95_ms: float | None = None


class MonitorUnitOut(BaseModel):
    name: str
    kind: Literal["docker", "systemd"]
    state: str
    health: str | None = None
    cpu_percent: float | None = None
    memory_bytes: int | None = None
    started_at: str | None = None
    uptime_seconds: int | None = None
    restart_count: int = 0
    level: Literal["ok", "warn", "error"]


class MonitorOperationOut(BaseModel):
    ts: str
    name: str
    status: Literal["ok", "warn", "error"]
    detail: str = ""


class MonitorStatusOut(BaseModel):
    collected_at: str
    overall: Literal["ok", "warn", "error"]
    warnings: list[str] = Field(default_factory=list)
    host: MonitorHostOut | None = None
    database: MonitorDatabaseOut | None = None
    app: MonitorAppOut | None = None
    units: list[MonitorUnitOut] = Field(default_factory=list)
    operations: list[MonitorOperationOut] = Field(default_factory=list)


@router.get("/status", response_model=MonitorStatusOut)
def get_monitor_status(
    _user: UserSession = Depends(require_admin),
) -> dict[str, Any]:
    return get_snapshot()
