"""Thin HTTP client for OSRM HTTP API.

Uses stdlib ``urllib`` (no extra deps), same pattern as ``app.letters.geocode``.
Supports ``nearest``, ``route``, and ``trip`` services.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class OsrmWaypoint:
    location: tuple[float, float]  # (lng, lat)
    distance: float = 0.0
    name: str = ""


@dataclass
class OsrmLeg:
    distance: float = 0.0  # metres
    duration: float = 0.0  # seconds


@dataclass
class OsrmRouteResult:
    """Result of a single /route/v1 or /trip/v1 call."""
    geometry_coords: list[tuple[float, float]] = field(default_factory=list)
    distance: float = 0.0
    duration: float = 0.0
    legs: list[OsrmLeg] = field(default_factory=list)
    waypoints: list[OsrmWaypoint] = field(default_factory=list)
    code: str = "Ok"
    raw: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Profile URL resolver
# ---------------------------------------------------------------------------

_PROFILE_ATTR = {
    "foot": "osrm_foot_url",
    "walking": "osrm_foot_url",
    "bicycle": "osrm_bike_url",
    "bike": "osrm_bike_url",
    "driving": "osrm_driving_url",
    "car": "osrm_driving_url",
}


def _base_url(profile: str) -> str:
    settings = get_settings()
    attr = _PROFILE_ATTR.get(profile)
    if not attr:
        raise ValueError(f"Unknown OSRM profile: {profile}")
    url: str = getattr(settings, attr)
    return url.rstrip("/")


def _timeout() -> float:
    return get_settings().osrm_timeout_seconds


# ---------------------------------------------------------------------------
# Low-level HTTP helpers
# ---------------------------------------------------------------------------

def _coords_str(coords: list[tuple[float, float]]) -> str:
    return ";".join(f"{lng},{lat}" for lng, lat in coords)


def _get_json(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=_timeout()) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        logger.error("OSRM HTTP %s: %s — %s", exc.code, url, body)
        raise
    except urllib.error.URLError as exc:
        logger.error("OSRM connection error: %s — %s", url, exc.reason)
        raise


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def nearest(
    profile: str,
    coord: tuple[float, float],
    *,
    number: int = 1,
) -> list[OsrmWaypoint]:
    """Find ``number`` nearest road-network points for *coord*."""
    base = _base_url(profile)
    url = f"{base}/nearest/v1/{profile}/{coord[0]},{coord[1]}?number={number}"
    data = _get_json(url)
    if data.get("code") != "Ok":
        logger.warning("OSRM nearest: %s", data.get("message", data.get("code")))
        return []
    result: list[OsrmWaypoint] = []
    for wp in data.get("waypoints", []):
        loc = wp.get("location", coord)
        result.append(OsrmWaypoint(
            location=(loc[0], loc[1]),
            distance=wp.get("distance", 0.0),
            name=wp.get("name", ""),
        ))
    return result


def route(
    profile: str,
    coords: list[tuple[float, float]],
    *,
    overview: str = "full",
    geometries: str = "geojson",
    steps: bool = False,
) -> OsrmRouteResult:
    """Build a route through *coords* (≥2 points)."""
    if len(coords) < 2:
        raise ValueError("route() requires at least 2 coordinates")
    base = _base_url(profile)
    cs = _coords_str(coords)
    params = urllib.parse.urlencode({
        "overview": overview,
        "geometries": geometries,
        "steps": "true" if steps else "false",
    })
    url = f"{base}/route/v1/{profile}/{cs}?{params}"
    data = _get_json(url)

    result = OsrmRouteResult(code=data.get("code", "Error"), raw=data)
    if result.code != "Ok":
        logger.warning("OSRM route: %s — %s", result.code, data.get("message", ""))
        return result

    routes = data.get("routes", [])
    if not routes:
        return result

    best = routes[0]
    result.distance = best.get("distance", 0.0)
    result.duration = best.get("duration", 0.0)

    geom = best.get("geometry", {})
    if isinstance(geom, dict):
        result.geometry_coords = [tuple(c) for c in geom.get("coordinates", [])]
    elif isinstance(geom, str):
        # polyline encoded — not expected with geojson param, but handle gracefully
        result.geometry_coords = []

    for leg_data in best.get("legs", []):
        result.legs.append(OsrmLeg(
            distance=leg_data.get("distance", 0.0),
            duration=leg_data.get("duration", 0.0),
        ))

    for wp in data.get("waypoints", []):
        loc = wp.get("location", [0, 0])
        result.waypoints.append(OsrmWaypoint(
            location=(loc[0], loc[1]),
            distance=wp.get("distance", 0.0),
            name=wp.get("name", ""),
        ))

    return result


def trip(
    profile: str,
    coords: list[tuple[float, float]],
    *,
    roundtrip: bool = False,
    source: str = "first",
    overview: str = "full",
    geometries: str = "geojson",
) -> OsrmRouteResult:
    """Solve a travelling-salesman ordering via OSRM Trip service."""
    if len(coords) < 2:
        raise ValueError("trip() requires at least 2 coordinates")
    base = _base_url(profile)
    cs = _coords_str(coords)
    params = urllib.parse.urlencode({
        "roundtrip": "true" if roundtrip else "false",
        "source": source,
        "overview": overview,
        "geometries": geometries,
    })
    url = f"{base}/trip/v1/{profile}/{cs}?{params}"
    data = _get_json(url)

    result = OsrmRouteResult(code=data.get("code", "Error"), raw=data)
    if result.code != "Ok":
        logger.warning("OSRM trip: %s — %s", result.code, data.get("message", ""))
        return result

    trips = data.get("trips", [])
    if not trips:
        return result

    best = trips[0]
    result.distance = best.get("distance", 0.0)
    result.duration = best.get("duration", 0.0)

    geom = best.get("geometry", {})
    if isinstance(geom, dict):
        result.geometry_coords = [tuple(c) for c in geom.get("coordinates", [])]

    for leg_data in best.get("legs", []):
        result.legs.append(OsrmLeg(
            distance=leg_data.get("distance", 0.0),
            duration=leg_data.get("duration", 0.0),
        ))

    # Trip returns waypoints with waypoint_index (the optimised order).
    for wp in data.get("waypoints", []):
        loc = wp.get("location", [0, 0])
        result.waypoints.append(OsrmWaypoint(
            location=(loc[0], loc[1]),
            distance=wp.get("distance", 0.0),
            name=wp.get("name", ""),
        ))

    return result
