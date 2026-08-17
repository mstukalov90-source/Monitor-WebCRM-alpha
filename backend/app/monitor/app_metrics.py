"""In-process HTTP latency counters for the admin monitor."""

from __future__ import annotations

from collections import deque
from threading import Lock
from time import monotonic, perf_counter
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

_SKIP_PATHS = frozenset({"/api/monitor/status", "/health"})
_MAX_SAMPLES = 500
_WINDOW_SECONDS = 60.0

_lock = Lock()
_latencies_ms: deque[tuple[float, float]] = deque(maxlen=_MAX_SAMPLES)


def record_request(elapsed_ms: float, *, now: float | None = None) -> None:
    ts = monotonic() if now is None else now
    with _lock:
        _latencies_ms.append((ts, elapsed_ms))


def clear_metrics() -> None:
    with _lock:
        _latencies_ms.clear()


def snapshot_request_metrics() -> dict[str, Any]:
    now = monotonic()
    cutoff = now - _WINDOW_SECONDS
    with _lock:
        recent = [ms for ts, ms in _latencies_ms if ts >= cutoff]
        all_samples = [ms for _, ms in _latencies_ms]
    samples = recent or all_samples
    return {
        "requests_per_minute": len(recent),
        "p95_ms": _percentile(samples, 95),
        "sample_count": len(samples),
    }


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((pct / 100) * (len(ordered) - 1)))))
    return round(ordered[index], 1)


class RequestMetricsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        start = perf_counter()
        response = await call_next(request)
        if request.url.path not in _SKIP_PATHS:
            record_request((perf_counter() - start) * 1000)
        return response
