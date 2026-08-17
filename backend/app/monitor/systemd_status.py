"""Read-only systemd unit status for WebCRM and nginx."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from typing import Any

from app.monitor.operations import record_operation

WATCHED_UNITS = ("monitor-webcrm", "nginx")
_SYSTEMCTL_TIMEOUT = 5.0
_seen_state: dict[str, str] = {}


def _run(args: list[str]) -> tuple[str, str | None]:
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=_SYSTEMCTL_TIMEOUT,
            check=False,
        )
    except FileNotFoundError:
        return "", "команда systemctl не найдена"
    except subprocess.TimeoutExpired:
        return "", "таймаут systemctl"
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return "", err or f"systemctl код {proc.returncode}"
    return proc.stdout, None


def parse_show_output(raw: str) -> dict[str, str]:
    props: dict[str, str] = {}
    for line in raw.splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        props[key.strip()] = value.strip()
    return props


def unit_from_props(name: str, props: dict[str, str]) -> dict[str, Any]:
    active = props.get("ActiveState") or "unknown"
    started_at = _parse_timestamp(
        props.get("ActiveEnterTimestamp") or props.get("ActiveEnterTimestampUSec")
    )
    memory_raw = props.get("MemoryCurrent")
    memory_bytes: int | None = None
    if memory_raw and memory_raw not in ("[not set]", "[no data]"):
        try:
            value = int(memory_raw)
            if value >= 0:
                memory_bytes = value
        except ValueError:
            memory_bytes = None
    restarts = 0
    try:
        restarts = int(props.get("NRestarts") or 0)
    except ValueError:
        restarts = 0
    level = "ok" if active == "active" else "error"
    uptime = None
    if active == "active" and started_at:
        try:
            ts = datetime.fromisoformat(started_at)
            uptime = max(0, int((datetime.now(timezone.utc) - ts).total_seconds()))
        except ValueError:
            uptime = None
    return {
        "name": name,
        "kind": "systemd",
        "state": active,
        "health": props.get("SubState") or None,
        "cpu_percent": None,
        "memory_bytes": memory_bytes,
        "started_at": started_at,
        "uptime_seconds": uptime,
        "restart_count": restarts,
        "level": level,
    }


def _parse_timestamp(raw: str | None) -> str | None:
    if not raw:
        return None
    text = raw.strip()
    if not text or text in ("n/a", "0", "[not set]"):
        return None
    if text.isdigit():
        usec = int(text)
        seconds = usec / 1_000_000 if usec > 10_000_000_000 else usec
        return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
    for fmt in (
        "%a %Y-%m-%d %H:%M:%S %Z",
        "%a %Y-%m-%d %H:%M:%S %z",
    ):
        try:
            dt = datetime.strptime(text, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            continue
    return text


def detect_service_changes(units: list[dict[str, Any]]) -> None:
    for unit in units:
        name = unit["name"]
        state = str(unit.get("state") or "")
        prev = _seen_state.get(name)
        if prev == "active" and state != "active":
            record_operation(f"systemd {name}", "error", f"сервис {state}")
        elif prev and prev != "active" and state == "active":
            record_operation(f"systemd {name}", "warn", "сервис перезапущен")
        _seen_state[name] = state


def reset_service_seen() -> None:
    _seen_state.clear()


def list_systemd_units() -> tuple[list[dict[str, Any]], str | None]:
    units: list[dict[str, Any]] = []
    last_error: str | None = None
    for name in WATCHED_UNITS:
        raw, err = _run(
            [
                "systemctl",
                "show",
                name,
                "-p",
                "Id",
                "-p",
                "ActiveState",
                "-p",
                "SubState",
                "-p",
                "ActiveEnterTimestamp",
                "-p",
                "NRestarts",
                "-p",
                "MemoryCurrent",
                "--no-pager",
            ]
        )
        if err:
            last_error = err
            units.append(
                {
                    "name": name,
                    "kind": "systemd",
                    "state": "unknown",
                    "health": None,
                    "cpu_percent": None,
                    "memory_bytes": None,
                    "started_at": None,
                    "uptime_seconds": None,
                    "restart_count": 0,
                    "level": "warn",
                }
            )
            continue
        units.append(unit_from_props(name, parse_show_output(raw)))
    detect_service_changes(units)
    if last_error and all(u["state"] == "unknown" for u in units):
        return [], last_error
    return units, None
