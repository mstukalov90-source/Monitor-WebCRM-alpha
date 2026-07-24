"""Reverse geocoding helpers for OATI letters."""

from __future__ import annotations

import json
import logging
import math
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from app.config import Settings

logger = logging.getLogger(__name__)

# Nominatim /search viewbox half-size when reverse has street but no house.
HOUSE_SEARCH_RADIUS_M = 250.0
HOUSE_SEARCH_LIMIT = 20


@dataclass
class GeocodeResult:
    """Nearest address parts for letter fill."""

    street: str = ""
    address: str = ""
    has_house: bool = False


def _road_from_address(address: dict[str, Any]) -> str:
    road = (
        address.get("road")
        or address.get("pedestrian")
        or address.get("residential")
        or address.get("street")
        or address.get("footway")
        or address.get("path")
        or address.get("suburb")
        or address.get("neighbourhood")
        or address.get("quarter")
    )
    return str(road).strip() if road else ""


def _house_from_address(address: dict[str, Any]) -> str:
    house = address.get("house_number") or address.get("housenumber")
    return str(house).strip() if house else ""


def format_street_house(address: dict[str, Any] | None) -> str | None:
    """Build «улица, дом» from Nominatim address parts."""
    if not address:
        return None
    road = _road_from_address(address)
    house = _house_from_address(address)
    parts = [p for p in (road, house) if p]
    if not parts:
        return None
    return ", ".join(parts)


def _nominatim_get(url: str, settings: Settings) -> dict[str, Any] | list[Any] | None:
    headers = {
        "User-Agent": settings.geocode_user_agent or "MONITOR-WebCRM/1.0",
        "Accept": "application/json",
    }
    timeout = float(settings.geocode_timeout_seconds or 8.0)
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        logger.warning("Nominatim request failed: %s", exc)
        return None


def _reverse_once(
    lon: float,
    lat: float,
    settings: Settings,
    *,
    zoom: int,
) -> dict[str, Any] | None:
    base = (settings.nominatim_url or "").strip()
    if not base:
        return None
    params = urllib.parse.urlencode(
        {
            "lat": f"{lat:.8f}",
            "lon": f"{lon:.8f}",
            "format": "json",
            "addressdetails": "1",
            "zoom": str(zoom),
            "accept-language": "ru",
        }
    )
    url = f"{base}?{params}" if "?" not in base else f"{base}&{params}"
    data = _nominatim_get(url, settings)
    return data if isinstance(data, dict) else None


def _search_nearest_house(
    lon: float,
    lat: float,
    street: str,
    settings: Settings,
) -> GeocodeResult | None:
    """Try Nominatim search for a nearby house on the same street."""
    base = (settings.nominatim_url or "").strip()
    if not base or not street:
        return None
    # Use /search endpoint derived from reverse URL host path.
    if base.rstrip("/").endswith("/reverse"):
        search_base = base.rstrip("/").rsplit("/", 1)[0] + "/search"
    else:
        search_base = base.rstrip("/") + "/search"

    # Viewbox around the point (meters → degrees).
    dlat = HOUSE_SEARCH_RADIUS_M / 111_320.0
    dlon = HOUSE_SEARCH_RADIUS_M / (111_320.0 * max(0.2, math.cos(math.radians(lat))))
    viewbox = f"{lon - dlon},{lat + dlat},{lon + dlon},{lat - dlat}"
    params = urllib.parse.urlencode(
        {
            "q": street,
            "format": "json",
            "addressdetails": "1",
            "limit": str(HOUSE_SEARCH_LIMIT),
            "viewbox": viewbox,
            "bounded": "1",
            "accept-language": "ru",
        }
    )
    data = _nominatim_get(f"{search_base}?{params}", settings)
    if not isinstance(data, list):
        return None

    best: tuple[float, GeocodeResult] | None = None
    for item in data:
        if not isinstance(item, dict):
            continue
        addr = item.get("address")
        if not isinstance(addr, dict):
            continue
        house = _house_from_address(addr)
        if not house:
            continue
        road = _road_from_address(addr) or street
        try:
            ilat = float(item.get("lat"))
            ilon = float(item.get("lon"))
        except (TypeError, ValueError):
            continue
        dist = (ilat - lat) ** 2 + (ilon - lon) ** 2
        result = GeocodeResult(
            street=road,
            address=f"{road}, {house}",
            has_house=True,
        )
        if best is None or dist < best[0]:
            best = (dist, result)
    return best[1] if best else None


def reverse_geocode_parts(
    lon: float,
    lat: float,
    settings: Settings,
) -> GeocodeResult:
    """Resolve nearest street and house. Prefers an address with house number."""
    # zoom 18 ≈ building; 17 ≈ street if building missing.
    for zoom in (18, 17):
        data = _reverse_once(lon, lat, settings, zoom=zoom)
        if not data:
            continue
        addr = data.get("address") if isinstance(data.get("address"), dict) else None
        if not addr:
            continue
        road = _road_from_address(addr)
        house = _house_from_address(addr)
        if road and house:
            return GeocodeResult(street=road, address=f"{road}, {house}", has_house=True)
        if road:
            nearby = _search_nearest_house(lon, lat, road, settings)
            if nearby:
                return nearby
            return GeocodeResult(street=road, address=road, has_house=False)

    return GeocodeResult()


def reverse_geocode_address(
    lon: float,
    lat: float,
    settings: Settings,
) -> str | None:
    """Resolve nearest street/house via Nominatim. Returns None on any failure."""
    result = reverse_geocode_parts(lon, lat, settings)
    return result.address or None
