"""Situational plan image at fixed map scale 1:1000."""

from __future__ import annotations

import io
import logging
import math
import urllib.error
import urllib.request
from typing import Any

from PIL import Image, ImageDraw

from app.config import Settings

logger = logging.getLogger(__name__)

# Printed map size in the DOCX (approximate usable A4 width).
MAP_WIDTH_CM = 16.0
MAP_HEIGHT_CM = 16.0
MAP_SCALE = 1000
# 1 cm on paper @ 1:1000 = 10 m on ground.
GROUND_WIDTH_M = MAP_WIDTH_CM * (MAP_SCALE / 100.0)
GROUND_HEIGHT_M = MAP_HEIGHT_CM * (MAP_SCALE / 100.0)

# Raster resolution for embedding (~150 dpi → 59 px/cm).
PX_PER_CM = 59
MAP_WIDTH_PX = int(MAP_WIDTH_CM * PX_PER_CM)
MAP_HEIGHT_PX = int(MAP_HEIGHT_CM * PX_PER_CM)

EARTH_RADIUS_M = 6378137.0
TILE_SIZE = 256


def _lonlat_to_mercator(lon: float, lat: float) -> tuple[float, float]:
    x = math.radians(lon) * EARTH_RADIUS_M
    lat_clamped = max(min(lat, 85.05112878), -85.05112878)
    y = math.log(math.tan(math.pi / 4.0 + math.radians(lat_clamped) / 2.0)) * EARTH_RADIUS_M
    return x, y


def _mercator_to_lonlat(x: float, y: float) -> tuple[float, float]:
    lon = math.degrees(x / EARTH_RADIUS_M)
    lat = math.degrees(2.0 * math.atan(math.exp(y / EARTH_RADIUS_M)) - math.pi / 2.0)
    return lon, lat


def map_bbox_mercator(center_lon: float, center_lat: float) -> tuple[float, float, float, float]:
    """Return (minx, miny, maxx, maxy) in Web Mercator meters for 1:1000 frame."""
    cx, cy = _lonlat_to_mercator(center_lon, center_lat)
    half_w = GROUND_WIDTH_M / 2.0
    half_h = GROUND_HEIGHT_M / 2.0
    return cx - half_w, cy - half_h, cx + half_w, cy + half_h


def _zoom_for_extent(minx: float, maxx: float, width_px: int) -> int:
    meters_per_pixel = (maxx - minx) / max(width_px, 1)
    # At equator: resolution = 156543.03392 / 2^z
    if meters_per_pixel <= 0:
        return 18
    z = math.log2(156543.03392 / meters_per_pixel)
    return max(1, min(19, int(round(z))))


def _tile_xy(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    n = 2**zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def _tile_bounds_mercator(tx: int, ty: int, zoom: int) -> tuple[float, float, float, float]:
    n = 2**zoom
    lon_min = tx / n * 360.0 - 180.0
    lon_max = (tx + 1) / n * 360.0 - 180.0
    lat_max = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * ty / n))))
    lat_min = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (ty + 1) / n))))
    x0, y0 = _lonlat_to_mercator(lon_min, lat_min)
    x1, y1 = _lonlat_to_mercator(lon_max, lat_max)
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def _fetch_tile(url_template: str, z: int, x: int, y: int, settings: Settings) -> Image.Image | None:
    url = (
        url_template.replace("{z}", str(z))
        .replace("{x}", str(x))
        .replace("{y}", str(y))
        .replace("{s}", "a")
    )
    headers = {"User-Agent": settings.geocode_user_agent or "MONITOR-WebCRM/1.0"}
    timeout = float(settings.geocode_timeout_seconds or 8.0)
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        return Image.open(io.BytesIO(data)).convert("RGB")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("OSM tile fetch failed %s/%s/%s: %s", z, x, y, exc)
        return None


def _mercator_to_pixel(
    x: float,
    y: float,
    bbox: tuple[float, float, float, float],
    width: int,
    height: int,
) -> tuple[float, float]:
    minx, miny, maxx, maxy = bbox
    px = (x - minx) / (maxx - minx) * width
    py = (maxy - y) / (maxy - miny) * height
    return px, py


def _clip_segment(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    w: int,
    h: int,
) -> tuple[float, float, float, float] | None:
    """Cohen–Sutherland clip of a segment to [0,w]x[0,h]."""
    LEFT, RIGHT, BOTTOM, TOP = 1, 2, 4, 8

    def code(x: float, y: float) -> int:
        c = 0
        if x < 0:
            c |= LEFT
        elif x > w:
            c |= RIGHT
        if y < 0:
            c |= TOP
        elif y > h:
            c |= BOTTOM
        return c

    c0, c1 = code(x0, y0), code(x1, y1)
    while True:
        if not (c0 | c1):
            return x0, y0, x1, y1
        if c0 & c1:
            return None
        c_out = c0 or c1
        if c_out & TOP:
            x = x0 + (x1 - x0) * (0 - y0) / (y1 - y0) if y1 != y0 else x0
            y = 0.0
        elif c_out & BOTTOM:
            x = x0 + (x1 - x0) * (h - y0) / (y1 - y0) if y1 != y0 else x0
            y = float(h)
        elif c_out & RIGHT:
            y = y0 + (y1 - y0) * (w - x0) / (x1 - x0) if x1 != x0 else y0
            x = float(w)
        else:
            y = y0 + (y1 - y0) * (0 - x0) / (x1 - x0) if x1 != x0 else y0
            x = 0.0
        if c_out == c0:
            x0, y0 = x, y
            c0 = code(x0, y0)
        else:
            x1, y1 = x, y
            c1 = code(x1, y1)


def _iter_coords(geom: dict[str, Any]) -> list[tuple[float, float]]:
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    points: list[tuple[float, float]] = []

    def walk(node: Any, depth: int) -> None:
        if not isinstance(node, (list, tuple)) or not node:
            return
        if depth == 0 and len(node) >= 2 and isinstance(node[0], (int, float)):
            points.append((float(node[0]), float(node[1])))
            return
        for child in node:
            walk(child, depth - 1)

    depth_by_type = {
        "Point": 0,
        "MultiPoint": 1,
        "LineString": 1,
        "MultiLineString": 2,
        "Polygon": 2,
        "MultiPolygon": 3,
    }
    if gtype in depth_by_type:
        walk(coords, depth_by_type[gtype])
    return points


def _iter_rings_or_lines(geom: dict[str, Any]) -> list[list[tuple[float, float]]]:
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    lines: list[list[tuple[float, float]]] = []

    def as_pts(seq: Any) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        for p in seq or []:
            if isinstance(p, (list, tuple)) and len(p) >= 2:
                out.append((float(p[0]), float(p[1])))
        return out

    if gtype == "LineString":
        lines.append(as_pts(coords))
    elif gtype == "MultiLineString":
        for line in coords or []:
            lines.append(as_pts(line))
    elif gtype == "Polygon":
        for ring in coords or []:
            lines.append(as_pts(ring))
    elif gtype == "MultiPolygon":
        for poly in coords or []:
            for ring in poly or []:
                lines.append(as_pts(ring))
    elif gtype == "Point":
        if isinstance(coords, (list, tuple)) and len(coords) >= 2:
            lines.append([(float(coords[0]), float(coords[1]))])
    elif gtype == "MultiPoint":
        for p in coords or []:
            if isinstance(p, (list, tuple)) and len(p) >= 2:
                lines.append([(float(p[0]), float(p[1]))])
    return lines


def classify_geometry_visibility(
    geometry: dict[str, Any] | None,
    center_lon: float,
    center_lat: float,
) -> str:
    """Return 'inside' | 'partial' | 'outside' | 'missing' relative to 1:1000 frame."""
    if not geometry:
        return "missing"
    bbox = map_bbox_mercator(center_lon, center_lat)
    minx, miny, maxx, maxy = bbox
    points = _iter_coords(geometry)
    if not points:
        return "missing"
    inside = 0
    outside = 0
    for lon, lat in points:
        x, y = _lonlat_to_mercator(lon, lat)
        if minx <= x <= maxx and miny <= y <= maxy:
            inside += 1
        else:
            outside += 1
    if inside and not outside:
        return "inside"
    if outside and not inside:
        return "outside"
    return "partial"


def render_situational_map(
    center_lon: float,
    center_lat: float,
    task_geometry: dict[str, Any] | None,
    settings: Settings,
) -> bytes:
    """Render PNG bytes: OSM tiles + report marker + clipped task geometry."""
    bbox = map_bbox_mercator(center_lon, center_lat)
    minx, miny, maxx, maxy = bbox
    width, height = MAP_WIDTH_PX, MAP_HEIGHT_PX
    zoom = _zoom_for_extent(minx, maxx, width)

    lon_sw, lat_sw = _mercator_to_lonlat(minx, miny)
    lon_ne, lat_ne = _mercator_to_lonlat(maxx, maxy)
    tx0, ty1 = _tile_xy(lon_sw, lat_sw, zoom)
    tx1, ty0 = _tile_xy(lon_ne, lat_ne, zoom)
    # y increases southward in TMS/OSM
    tminx, tmaxx = min(tx0, tx1), max(tx0, tx1)
    tminy, tmaxy = min(ty0, ty1), max(ty0, ty1)

    canvas = Image.new("RGB", (width, height), color=(230, 230, 230))
    template = settings.osm_tile_url or "https://tile.openstreetmap.org/{z}/{x}/{y}.png"

    for ty in range(tminy, tmaxy + 1):
        for tx in range(tminx, tmaxx + 1):
            tile = _fetch_tile(template, zoom, tx, ty, settings)
            if tile is None:
                continue
            tmin_x, tmin_y, tmax_x, tmax_y = _tile_bounds_mercator(tx, ty, zoom)
            # Paste tile into canvas using mercator → pixel mapping of corners.
            px0, py0 = _mercator_to_pixel(tmin_x, tmax_y, bbox, width, height)
            px1, py1 = _mercator_to_pixel(tmax_x, tmin_y, bbox, width, height)
            dest_w = max(1, int(round(px1 - px0)))
            dest_h = max(1, int(round(py1 - py0)))
            resized = tile.resize((dest_w, dest_h), Image.Resampling.BILINEAR)
            canvas.paste(resized, (int(round(px0)), int(round(py0))))

    draw = ImageDraw.Draw(canvas)

    # Task geometry (blue), clipped to frame.
    if task_geometry:
        for line in _iter_rings_or_lines(task_geometry):
            if len(line) == 1:
                lon, lat = line[0]
                x, y = _lonlat_to_mercator(lon, lat)
                px, py = _mercator_to_pixel(x, y, bbox, width, height)
                if 0 <= px <= width and 0 <= py <= height:
                    r = 6
                    draw.ellipse((px - r, py - r, px + r, py + r), fill=(30, 90, 200), outline=(0, 40, 120))
                continue
            for i in range(len(line) - 1):
                lon0, lat0 = line[i]
                lon1, lat1 = line[i + 1]
                x0, y0 = _lonlat_to_mercator(lon0, lat0)
                x1, y1 = _lonlat_to_mercator(lon1, lat1)
                p0 = _mercator_to_pixel(x0, y0, bbox, width, height)
                p1 = _mercator_to_pixel(x1, y1, bbox, width, height)
                clipped = _clip_segment(p0[0], p0[1], p1[0], p1[1], width, height)
                if clipped:
                    draw.line(
                        (clipped[0], clipped[1], clipped[2], clipped[3]),
                        fill=(30, 90, 200),
                        width=3,
                    )

    # Report center marker (red).
    cx, cy = _lonlat_to_mercator(center_lon, center_lat)
    px, py = _mercator_to_pixel(cx, cy, bbox, width, height)
    r = 8
    draw.ellipse((px - r, py - r, px + r, py + r), fill=(220, 40, 40), outline=(120, 0, 0), width=2)
    draw.line((px, py - 14, px, py + 14), fill=(120, 0, 0), width=2)
    draw.line((px - 14, py, px + 14, py), fill=(120, 0, 0), width=2)

    # Scale bar legend.
    bar_m = 50
    bar_px = bar_m / GROUND_WIDTH_M * width
    margin = 20
    y_bar = height - margin
    x0 = margin
    x1 = margin + bar_px
    draw.rectangle((x0, y_bar - 4, x1, y_bar), fill=(0, 0, 0))
    draw.text((x0, y_bar - 22), f"0", fill=(0, 0, 0))
    draw.text((x1 - 10, y_bar - 22), f"{bar_m} м", fill=(0, 0, 0))
    draw.text((margin, margin), "Масштаб 1:1000", fill=(0, 0, 0))

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()
