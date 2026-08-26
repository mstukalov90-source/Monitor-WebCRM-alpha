"""Situational plan image at a selectable map scale (default 1:1000)."""

from __future__ import annotations

import io
import logging
import math
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.config import Settings

logger = logging.getLogger(__name__)

# Printed map size in the DOCX (approximate usable A4 width).
MAP_WIDTH_CM = 16.0
MAP_HEIGHT_CM = 16.0
ALLOWED_MAP_SCALES = (1000, 2000, 5000, 10000)
DEFAULT_MAP_SCALE = 1000
MAP_SCALE = DEFAULT_MAP_SCALE  # backward-compatible alias
# 1 cm on paper @ 1:1000 = 10 m on ground.
GROUND_WIDTH_M = MAP_WIDTH_CM * (MAP_SCALE / 100.0)
GROUND_HEIGHT_M = MAP_HEIGHT_CM * (MAP_SCALE / 100.0)

# Raster resolution for embedding (~150 dpi → 59 px/cm).
PX_PER_CM = 59
MAP_WIDTH_PX = int(MAP_WIDTH_CM * PX_PER_CM)
MAP_HEIGHT_PX = int(MAP_HEIGHT_CM * PX_PER_CM)

EARTH_RADIUS_M = 6378137.0
TILE_SIZE = 256

REPORT_MARKER_PATH = Path(__file__).resolve().parent / "templates" / "report.png"
# Marker width on the rendered PNG (~printed ~0.7 cm at 59 px/cm).
REPORT_MARKER_WIDTH_PX = 42

# App basemap «1:2000» (mapBasemap.ts). Do not use OSM_TILE_URL — prod .env stays on «Схема».
LETTER_TILE_URL = (
    "http://ngtst.mggt:8080/api/component/render/tile"
    "?resource=232992&nd=204&z={z}&x={x}&y={y}"
)

_CYRILLIC_FONT_CANDIDATES = (
    Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/liberation/LiberationSans-Regular.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    Path("/usr/share/fonts/liberation-sans/LiberationSans-Regular.ttf"),
    Path("/Library/Fonts/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
)


def ground_width_m(scale: int = DEFAULT_MAP_SCALE) -> float:
    """Ground width covered by the printed map frame at the given scale."""
    return MAP_WIDTH_CM * (scale / 100.0)


def ground_height_m(scale: int = DEFAULT_MAP_SCALE) -> float:
    return MAP_HEIGHT_CM * (scale / 100.0)


def normalize_map_scale(scale: int | None) -> int:
    """Return a whitelisted scale or raise ValueError."""
    value = DEFAULT_MAP_SCALE if scale is None else int(scale)
    if value not in ALLOWED_MAP_SCALES:
        allowed = ", ".join(str(s) for s in ALLOWED_MAP_SCALES)
        raise ValueError(f"Недопустимый масштаб карты: {value}. Допустимо: {allowed}")
    return value


def _overlay_scale_labels(scale: int, *, has_font: bool | None = None) -> tuple[str, str]:
    """Cyrillic labels when a TTF is available; ASCII Scale/M otherwise."""
    bar_m = _scale_bar_meters(scale)
    if has_font is None:
        has_font = _map_overlay_font(16) is not None
    if has_font:
        return f"Масштаб 1:{scale}", f"{bar_m} м"
    return f"Scale 1:{scale}", f"{bar_m} M"


def _scale_bar_meters(scale: int) -> int:
    """Pick a round scale-bar length that fits ~1/4 of the frame width."""
    target = ground_width_m(scale) / 4.0
    candidates = (10, 20, 50, 100, 200, 500, 1000, 2000)
    return min(candidates, key=lambda c: abs(c - target))


@lru_cache(maxsize=1)
def _map_overlay_font(size: int = 16) -> ImageFont.FreeTypeFont | ImageFont.ImageFont | None:
    """TrueType with Cyrillic if available; None means use the bitmap default font."""
    for path in _CYRILLIC_FONT_CANDIDATES:
        if not path.is_file():
            continue
        try:
            return ImageFont.truetype(str(path), size=size)
        except OSError:
            continue
    return None


@lru_cache(maxsize=1)
def _load_report_marker() -> Image.Image:
    """Load and resize the report.png marker (RGBA with transparency)."""
    if not REPORT_MARKER_PATH.is_file():
        raise FileNotFoundError(f"Report marker not found: {REPORT_MARKER_PATH}")
    icon = Image.open(REPORT_MARKER_PATH).convert("RGBA")
    w, h = icon.size
    if w <= 0 or h <= 0:
        raise ValueError("Report marker has invalid size")
    new_w = REPORT_MARKER_WIDTH_PX
    new_h = max(1, int(round(h * (new_w / w))))
    return icon.resize((new_w, new_h), Image.Resampling.LANCZOS)


def _paste_report_marker(canvas: Image.Image, px: float, py: float) -> None:
    """Paste report.png centered on (px, py); fall back to a red cross if missing."""
    try:
        marker = _load_report_marker()
    except (OSError, ValueError) as exc:
        logger.warning("Cannot load report marker, using red cross: %s", exc)
        draw = ImageDraw.Draw(canvas)
        r = 8
        draw.ellipse((px - r, py - r, px + r, py + r), fill=(220, 40, 40), outline=(120, 0, 0), width=2)
        draw.line((px, py - 14, px, py + 14), fill=(120, 0, 0), width=2)
        draw.line((px - 14, py, px + 14, py), fill=(120, 0, 0), width=2)
        return

    mw, mh = marker.size
    left = int(round(px - mw / 2))
    top = int(round(py - mh / 2))
    cw, ch = canvas.size
    # Clip marker to canvas bounds.
    src_l = max(0, -left)
    src_t = max(0, -top)
    src_r = min(mw, cw - left)
    src_b = min(mh, ch - top)
    if src_r <= src_l or src_b <= src_t:
        return
    cropped = marker.crop((src_l, src_t, src_r, src_b))
    dest = (left + src_l, top + src_t)
    if canvas.mode != "RGBA":
        base = canvas.convert("RGBA")
        base.alpha_composite(cropped, dest)
        canvas.paste(base.convert("RGB"))
    else:
        canvas.alpha_composite(cropped, dest)


def _lonlat_to_mercator(lon: float, lat: float) -> tuple[float, float]:
    x = math.radians(lon) * EARTH_RADIUS_M
    lat_clamped = max(min(lat, 85.05112878), -85.05112878)
    y = math.log(math.tan(math.pi / 4.0 + math.radians(lat_clamped) / 2.0)) * EARTH_RADIUS_M
    return x, y


def _mercator_to_lonlat(x: float, y: float) -> tuple[float, float]:
    lon = math.degrees(x / EARTH_RADIUS_M)
    lat = math.degrees(2.0 * math.atan(math.exp(y / EARTH_RADIUS_M)) - math.pi / 2.0)
    return lon, lat


def map_bbox_mercator(
    center_lon: float,
    center_lat: float,
    scale: int = DEFAULT_MAP_SCALE,
) -> tuple[float, float, float, float]:
    """Return (minx, miny, maxx, maxy) in Web Mercator meters for the map frame."""
    cx, cy = _lonlat_to_mercator(center_lon, center_lat)
    half_w = ground_width_m(scale) / 2.0
    half_h = ground_height_m(scale) / 2.0
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
    scale: int = DEFAULT_MAP_SCALE,
) -> str:
    """Return 'inside' | 'partial' | 'outside' | 'missing' relative to the map frame."""
    if not geometry:
        return "missing"
    bbox = map_bbox_mercator(center_lon, center_lat, scale=scale)
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
    scale: int = DEFAULT_MAP_SCALE,
) -> bytes:
    """Render PNG bytes: basemap tiles + report marker + clipped task geometry."""
    scale = normalize_map_scale(scale)
    bbox = map_bbox_mercator(center_lon, center_lat, scale=scale)
    minx, miny, maxx, maxy = bbox
    width, height = MAP_WIDTH_PX, MAP_HEIGHT_PX
    zoom = _zoom_for_extent(minx, maxx, width)
    gw = ground_width_m(scale)


    lon_sw, lat_sw = _mercator_to_lonlat(minx, miny)
    lon_ne, lat_ne = _mercator_to_lonlat(maxx, maxy)
    tx0, ty1 = _tile_xy(lon_sw, lat_sw, zoom)
    tx1, ty0 = _tile_xy(lon_ne, lat_ne, zoom)
    # y increases southward in TMS/OSM
    tminx, tmaxx = min(tx0, tx1), max(tx0, tx1)
    tminy, tmaxy = min(ty0, ty1), max(ty0, ty1)

    canvas = Image.new("RGB", (width, height), color=(230, 230, 230))
    template = LETTER_TILE_URL

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

    # Report center marker (report.png roadwork sign).
    cx, cy = _lonlat_to_mercator(center_lon, center_lat)
    px, py = _mercator_to_pixel(cx, cy, bbox, width, height)
    _paste_report_marker(canvas, px, py)

    # Scale bar legend (redraw on top of marker if they overlap).
    draw = ImageDraw.Draw(canvas)
    bar_m = _scale_bar_meters(scale)
    bar_px = bar_m / gw * width
    margin = 20
    y_bar = height - margin
    x0 = margin
    x1 = margin + bar_px
    draw.rectangle((x0, y_bar - 4, x1, y_bar), fill=(0, 0, 0))
    font = _map_overlay_font(16)
    scale_label, bar_end = _overlay_scale_labels(scale, has_font=font is not None)
    draw.text((x0, y_bar - 22), "0", fill=(0, 0, 0), font=font)
    draw.text((x1 - 10, y_bar - 22), bar_end, fill=(0, 0, 0), font=font)
    draw.text((margin, margin), scale_label, fill=(0, 0, 0), font=font)

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()
