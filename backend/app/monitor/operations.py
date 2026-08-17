"""In-memory ring buffer of recent operational events."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Literal

OperationStatus = Literal["ok", "warn", "error"]

MAX_OPERATIONS = 50

_lock = Lock()
_operations: deque[dict[str, Any]] = deque(maxlen=MAX_OPERATIONS)


def record_operation(name: str, status: OperationStatus, detail: str = "") -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "name": name,
        "status": status,
        "detail": detail,
    }
    with _lock:
        _operations.append(entry)


def list_operations() -> list[dict[str, Any]]:
    with _lock:
        return list(reversed(_operations))


def clear_operations() -> None:
    with _lock:
        _operations.clear()
