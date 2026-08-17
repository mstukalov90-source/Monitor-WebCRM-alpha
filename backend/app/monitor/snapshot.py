"""Assemble a cached admin monitor snapshot."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Any

from app.config import get_settings
from app.db import get_connection, pool_usage
from app.monitor.app_metrics import snapshot_request_metrics
from app.monitor.docker_status import list_docker_containers
from app.monitor.operations import list_operations
from app.monitor.systemd_status import list_systemd_units

CACHE_TTL_SECONDS = 5.0
SLOW_QUERY_SECONDS = 5
DISK_WARN_PCT = 90.0
DISK_ERROR_PCT = 95.0
RAM_WARN_PCT = 90.0
CPU_WARN_PCT = 85.0
DB_CONN_WARN_PCT = 80.0
DB_CONN_ERROR_PCT = 90.0

_cache_lock = Lock()
_cached: dict[str, Any] | None = None
_cached_at = 0.0


def get_snapshot(*, force: bool = False) -> dict[str, Any]:
    global _cached, _cached_at
    now = monotonic()
    with _cache_lock:
        if not force and _cached is not None and now - _cached_at < CACHE_TTL_SECONDS:
            return _cached
        snap = collect_snapshot()
        _cached = snap
        _cached_at = now
        return snap


def clear_snapshot_cache() -> None:
    global _cached, _cached_at
    with _cache_lock:
        _cached = None
        _cached_at = 0.0


def collect_snapshot() -> dict[str, Any]:
    warnings: list[str] = []
    host = _host_metrics(warnings)
    database = _database_metrics(warnings)
    app = _app_metrics(warnings)
    docker_units, docker_err = list_docker_containers()
    if docker_err:
        warnings.append(f"Docker: {docker_err}")
    systemd_units, systemd_err = list_systemd_units()
    if systemd_err:
        warnings.append(f"systemd: {systemd_err}")
    units = docker_units + systemd_units
    overall = _overall_level(host, database, units)
    return {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "overall": overall,
        "warnings": warnings,
        "host": host,
        "database": database,
        "app": app,
        "units": units,
        "operations": list_operations(),
    }


def _host_metrics(warnings: list[str]) -> dict[str, Any] | None:
    try:
        import psutil
    except ImportError:
        warnings.append("psutil не установлен")
        return None
    try:
        cpu = float(psutil.cpu_percent(interval=0.15))
        vm = psutil.virtual_memory()
        load: list[float] | None
        try:
            load = [round(x, 2) for x in os.getloadavg()]
        except OSError:
            load = None
        disks = [_disk_usage("/", "корень")]
        settings = get_settings()
        for path, label in (
            (settings.photo_storage_dir, "фото"),
            (settings.field_photo_storage_dir, "полевые фото"),
        ):
            disk = _disk_usage(path, label)
            if disk is not None:
                disks.append(disk)
        return {
            "cpu_percent": round(cpu, 1),
            "loadavg": load,
            "memory_used_bytes": int(vm.used),
            "memory_total_bytes": int(vm.total),
            "memory_percent": round(float(vm.percent), 1),
            "disks": [d for d in disks if d is not None],
        }
    except Exception as exc:
        warnings.append(f"хост: {exc}")
        return None


def _disk_usage(path: str, label: str) -> dict[str, Any] | None:
    target = Path(path)
    if path != "/" and not target.exists():
        return None
    try:
        import psutil

        usage = psutil.disk_usage(str(target))
    except OSError:
        return None
    return {
        "path": str(target),
        "label": label,
        "used_bytes": int(usage.used),
        "total_bytes": int(usage.total),
        "percent": round(float(usage.percent), 1),
    }


def _database_metrics(warnings: list[str]) -> dict[str, Any] | None:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT numbackends, blks_hit, blks_read
                    FROM pg_stat_database
                    WHERE datname = current_database()
                    """
                )
                db_row = cur.fetchone()
                cur.execute(
                    "SELECT setting::int FROM pg_settings WHERE name = 'max_connections'"
                )
                max_row = cur.fetchone()
                cur.execute("SELECT pg_database_size(current_database())")
                size_row = cur.fetchone()
                cur.execute(
                    """
                    SELECT
                      count(*) FILTER (WHERE state = 'active') AS active,
                      count(*) AS total
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                    """
                )
                act_row = cur.fetchone()
                cur.execute(
                    f"""
                    SELECT
                      pid,
                      EXTRACT(EPOCH FROM (now() - query_start)) AS duration_s,
                      left(query, 120) AS query
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                      AND state = 'active'
                      AND pid <> pg_backend_pid()
                      AND now() - query_start > interval '{SLOW_QUERY_SECONDS} seconds'
                    ORDER BY query_start
                    LIMIT 10
                    """
                )
                slow_rows = cur.fetchall()
    except Exception as exc:
        warnings.append(f"БД: {exc}")
        return None

    backends = int(db_row[0] or 0) if db_row else 0
    blks_hit = int(db_row[1] or 0) if db_row else 0
    blks_read = int(db_row[2] or 0) if db_row else 0
    hit_total = blks_hit + blks_read
    cache_hit = round(100.0 * blks_hit / hit_total, 1) if hit_total else None
    max_conn = int(max_row[0]) if max_row and max_row[0] is not None else None
    size_bytes = int(size_row[0]) if size_row and size_row[0] is not None else 0
    active = int(act_row[0] or 0) if act_row else 0
    total = int(act_row[1] or 0) if act_row else backends
    slow = [
        {
            "pid": int(row[0]),
            "duration_seconds": round(float(row[1] or 0), 1),
            "query": str(row[2] or ""),
        }
        for row in slow_rows
    ]
    return {
        "connections": total,
        "max_connections": max_conn,
        "active_queries": active,
        "cache_hit_percent": cache_hit,
        "size_bytes": size_bytes,
        "slow_queries": slow,
    }


def _app_metrics(warnings: list[str]) -> dict[str, Any]:
    http = snapshot_request_metrics()
    rss: int | None = None
    cpu: float | None = None
    try:
        import psutil

        proc = psutil.Process()
        rss = int(proc.memory_info().rss)
        cpu = round(float(proc.cpu_percent(interval=None)), 1)
    except Exception as exc:
        warnings.append(f"процесс WebCRM: {exc}")
    pool = pool_usage()
    return {
        "status": "active",
        "rss_bytes": rss,
        "cpu_percent": cpu,
        "pool_in_use": pool["in_use"],
        "pool_max": pool["max"],
        "requests_per_minute": http["requests_per_minute"],
        "p95_ms": http["p95_ms"],
    }


def _overall_level(
    host: dict[str, Any] | None,
    database: dict[str, Any] | None,
    units: list[dict[str, Any]],
) -> str:
    level = "ok"
    if any(u.get("level") == "error" for u in units):
        return "error"
    if any(u.get("level") == "warn" for u in units):
        level = "warn"
    if host:
        if float(host.get("cpu_percent") or 0) >= CPU_WARN_PCT:
            level = "warn"
        if float(host.get("memory_percent") or 0) >= RAM_WARN_PCT:
            level = "warn"
        for disk in host.get("disks") or []:
            pct = float(disk.get("percent") or 0)
            if pct >= DISK_ERROR_PCT:
                return "error"
            if pct >= DISK_WARN_PCT:
                level = "warn"
    if database:
        max_conn = database.get("max_connections")
        used = database.get("connections") or 0
        if max_conn:
            pct = 100.0 * used / max_conn
            if pct >= DB_CONN_ERROR_PCT:
                return "error"
            if pct >= DB_CONN_WARN_PCT:
                level = "warn"
        if database.get("slow_queries"):
            level = "warn"
    return level
