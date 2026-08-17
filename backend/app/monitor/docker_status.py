"""Read-only Docker container status via the docker CLI."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from typing import Any

from app.monitor.operations import record_operation

_DOCKER_TIMEOUT = 8.0
_seen_started: dict[str, str] = {}
_seen_state: dict[str, str] = {}


def _run(args: list[str], timeout: float = _DOCKER_TIMEOUT) -> tuple[str, str | None]:
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return "", "команда docker не найдена"
    except subprocess.TimeoutExpired:
        return "", "таймаут docker"
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return "", err or f"docker код {proc.returncode}"
    return proc.stdout, None


def parse_percent(value: str | None) -> float | None:
    if not value:
        return None
    text = value.strip().rstrip("%")
    try:
        return float(text)
    except ValueError:
        return None


def parse_mem_used_bytes(usage: str | None) -> int | None:
    if not usage:
        return None
    used = usage.split("/", 1)[0].strip()
    return _parse_size(used)


def _parse_size(text: str) -> int | None:
    cleaned = text.strip().replace(",", ".")
    if not cleaned:
        return None
    number = ""
    unit = ""
    for ch in cleaned:
        if ch.isdigit() or ch == ".":
            number += ch
        else:
            unit += ch
    try:
        value = float(number)
    except ValueError:
        return None
    unit = unit.strip().lower()
    multipliers = {
        "b": 1,
        "kb": 1000,
        "mb": 1000**2,
        "gb": 1000**3,
        "tb": 1000**4,
        "kib": 1024,
        "mib": 1024**2,
        "gib": 1024**3,
        "tib": 1024**4,
    }
    factor = multipliers.get(unit, 1)
    return int(value * factor)


def health_from_state(state: dict[str, Any]) -> str | None:
    health = state.get("Health")
    if isinstance(health, dict):
        status = health.get("Status")
        if isinstance(status, str) and status:
            return status
    return None


def level_for_container(state: str, health: str | None) -> str:
    if state != "running":
        return "error"
    if health == "unhealthy":
        return "error"
    if health in ("starting",):
        return "warn"
    return "ok"


def containers_from_inspect(
    inspect_payload: list[dict[str, Any]],
    stats_by_name: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for item in inspect_payload:
        name = str(item.get("Name") or "").lstrip("/")
        if not name:
            continue
        state = item.get("State") or {}
        status = str(state.get("Status") or "unknown")
        started_at = str(state.get("StartedAt") or "")
        health = health_from_state(state)
        stats = stats_by_name.get(name, {})
        cpu = parse_percent(stats.get("CPUPerc") or stats.get("CPUPercentage"))
        mem_bytes = parse_mem_used_bytes(stats.get("MemUsage"))
        restart_count = int(state.get("RestartCount") or 0)
        units.append(
            {
                "name": name,
                "kind": "docker",
                "state": status,
                "health": health,
                "cpu_percent": cpu,
                "memory_bytes": mem_bytes,
                "started_at": started_at or None,
                "uptime_seconds": _uptime_seconds(started_at) if status == "running" else None,
                "restart_count": restart_count,
                "level": level_for_container(status, health),
            }
        )
    units.sort(key=lambda u: u["name"])
    return units


def _uptime_seconds(started_at: str) -> int | None:
    if not started_at or started_at.startswith("0001-01-01"):
        return None
    try:
        ts = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - ts).total_seconds()))


def _stats_by_name(raw: str) -> dict[str, dict[str, Any]]:
    by_name: dict[str, dict[str, Any]] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = str(row.get("Name") or row.get("name") or "").lstrip("/")
        if name:
            by_name[name] = row
    return by_name


def detect_container_changes(units: list[dict[str, Any]]) -> None:
    for unit in units:
        name = unit["name"]
        started = unit.get("started_at") or ""
        state = str(unit.get("state") or "")
        prev_started = _seen_started.get(name)
        prev_state = _seen_state.get(name)
        if prev_started and started and started != prev_started and state == "running":
            record_operation(f"docker {name}", "warn", "контейнер перезапущен")
        if prev_state == "running" and state != "running":
            record_operation(f"docker {name}", "error", f"контейнер {state}")
        if started:
            _seen_started[name] = started
        _seen_state[name] = state


def reset_container_seen() -> None:
    _seen_started.clear()
    _seen_state.clear()


def list_docker_containers() -> tuple[list[dict[str, Any]], str | None]:
    ids_out, ids_err = _run(["docker", "ps", "-aq"])
    if ids_err:
        return [], ids_err
    ids = [line.strip() for line in ids_out.splitlines() if line.strip()]
    if not ids:
        return [], None
    inspect_out, inspect_err = _run(["docker", "inspect", *ids], timeout=12.0)
    if inspect_err:
        return [], inspect_err
    try:
        payload = json.loads(inspect_out)
    except json.JSONDecodeError:
        return [], "некорректный ответ docker inspect"
    if not isinstance(payload, list):
        payload = [payload]
    stats_out, _stats_err = _run(
        ["docker", "stats", "--no-stream", "--format", "{{json .}}"],
        timeout=12.0,
    )
    stats = _stats_by_name(stats_out) if stats_out else {}
    units = containers_from_inspect(payload, stats)
    detect_container_changes(units)
    return units, None
