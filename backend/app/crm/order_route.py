"""Build a planned survey route for an area order via OSRM.

The route must:
1. Pass within ``buffer_m`` metres of every task inside the order polygon.
2. With a ``buffer_m`` buffer, cover the entire order polygon.

Because real road networks have gaps (closed courtyards, etc.) full coverage
is not always achievable.  The builder iteratively adds waypoints for uncovered
zones and reports the actual coverage metrics and any uncovered geometry.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from typing import Any

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor, Json

from app.config import get_settings
from app.crm.tasks_area import _task_geom_union_sql  # noqa: WPS436 — reuse existing SQL helper

logger = logging.getLogger(__name__)

MAX_REFINE_ITERATIONS = 3
MAX_WAYPOINTS = 300
OSRM_TRIP_CHUNK = 90  # OSRM trip has a practical limit around 100 waypoints

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _metric_srid() -> int:
    from app.config import crm_tasks_config
    cfg = crm_tasks_config()
    metric_crs = cfg.get("metric_crs", "EPSG:32637")
    return int(metric_crs.split(":")[-1]) if ":" in metric_crs else 32637


class OrderRouteError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# DB queries
# ---------------------------------------------------------------------------

def _fetch_order(conn: PgConnection, order_key: str) -> dict[str, Any] | None:
    srid = _metric_srid()
    sql = f"""
        SELECT
            key::text AS order_key,
            task_number,
            rayon,
            ST_AsGeoJSON(geom)::json AS geometry,
            ST_AsText(ST_Transform(geom, {srid})) AS order_wkt,
            ST_Area(ST_Transform(geom, {srid})) AS order_area_m2
        FROM crm.tasks_area
        WHERE key = %s::uuid AND geom IS NOT NULL
        LIMIT 1
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, (order_key,))
        row = cur.fetchone()
    if not row:
        return None
    data = dict(row)
    geom = data.get("geometry")
    if isinstance(geom, str):
        data["geometry"] = json.loads(geom)
    return data


def _fetch_task_points(
    conn: PgConnection,
    order_wkt: str,
) -> list[tuple[float, float]]:
    """Return (lng, lat) for every task inside the order polygon."""
    srid = _metric_srid()
    geom_union = _task_geom_union_sql()
    sql = f"""
        WITH order_poly AS (
            SELECT ST_GeomFromText(%s, {srid}) AS geom
        )
        SELECT DISTINCT
            ST_X(ST_Transform(ST_PointOnSurface(g.geom), 4326)) AS lng,
            ST_Y(ST_Transform(ST_PointOnSurface(g.geom), 4326)) AS lat
        FROM ({geom_union}) g
        CROSS JOIN order_poly o
        WHERE g.geom IS NOT NULL
          AND NOT ST_IsEmpty(g.geom)
          AND ST_Intersects(ST_Transform(g.geom, {srid}), o.geom)
    """
    with conn.cursor() as cur:
        cur.execute(sql, (order_wkt,))
        return [
            (row[0], row[1])
            for row in cur.fetchall()
            if row[0] is not None and row[1] is not None
        ]


def _generate_coverage_grid(
    conn: PgConnection,
    order_wkt: str,
    spacing_m: float,
) -> list[tuple[float, float]]:
    """Generate a regular grid of points covering the polygon."""
    srid = _metric_srid()
    sql = f"""
        WITH order_poly AS (
            SELECT ST_GeomFromText(%s, {srid}) AS geom
        ),
        grid AS (
            SELECT (ST_DumpPoints(
                ST_GeneratePoints(o.geom, GREATEST(
                    CEIL(ST_Area(o.geom) / ({spacing_m} * {spacing_m}))::int,
                    4
                ))
            )).geom AS pt
            FROM order_poly o
        )
        SELECT
            ST_X(ST_Transform(ST_PointOnSurface(g.pt), 4326)) AS lng,
            ST_Y(ST_Transform(ST_PointOnSurface(g.pt), 4326)) AS lat
        FROM grid g
        WHERE g.pt IS NOT NULL AND NOT ST_IsEmpty(g.pt)
    """
    with conn.cursor() as cur:
        cur.execute(sql, (order_wkt,))
        return [(row[0], row[1]) for row in cur.fetchall()]


def _uncovered_centroids(
    conn: PgConnection,
    order_wkt: str,
    route_wkt_4326: str,
    buffer_m: float,
    max_points: int = 20,
) -> list[tuple[float, float]]:
    """Return centroids of uncovered patches inside the order polygon."""
    srid = _metric_srid()
    sql = f"""
        WITH order_poly AS (
            SELECT ST_GeomFromText(%s, {srid}) AS geom
        ),
        route_buf AS (
            SELECT ST_Buffer(
                ST_Transform(ST_GeomFromText(%s, 4326), {srid}),
                %s
            ) AS geom
        ),
        diff AS (
            SELECT ST_Difference(o.geom, rb.geom) AS geom
            FROM order_poly o, route_buf rb
        ),
        parts AS (
            SELECT (ST_Dump(d.geom)).geom AS geom
            FROM diff d
            WHERE NOT ST_IsEmpty(d.geom)
        )
        SELECT
            ST_X(ST_Transform(ST_PointOnSurface(p.geom), 4326)) AS lng,
            ST_Y(ST_Transform(ST_PointOnSurface(p.geom), 4326)) AS lat,
            ST_Area(p.geom) AS area_m2
        FROM parts p
        WHERE ST_Area(p.geom) > 10
          AND NOT ST_IsEmpty(p.geom)
        ORDER BY ST_Area(p.geom) DESC
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (order_wkt, route_wkt_4326, buffer_m, max_points))
        return [(row[0], row[1]) for row in cur.fetchall()]


def _validate_route(
    conn: PgConnection,
    order_wkt: str,
    route_wkt_4326: str,
    task_points_4326: list[tuple[float, float]],
    buffer_m: float,
) -> dict[str, Any]:
    """Compute coverage metrics for a built route."""
    srid = _metric_srid()
    # Polygon coverage
    sql_poly = f"""
        WITH order_poly AS (
            SELECT ST_GeomFromText(%s, {srid}) AS geom
        ),
        route_buf AS (
            SELECT ST_Buffer(
                ST_Transform(ST_GeomFromText(%s, 4326), {srid}),
                %s
            ) AS geom
        )
        SELECT
            CASE
                WHEN ST_Area(op.geom) = 0 THEN 100.0
                ELSE 100.0 * ST_Area(ST_Intersection(op.geom, rb.geom))
                     / ST_Area(op.geom)
            END AS pct,
            ST_AsGeoJSON(
                ST_Transform(ST_Difference(op.geom, rb.geom), 4326)
            )::json AS uncovered
        FROM order_poly op, route_buf rb
    """
    with conn.cursor() as cur:
        cur.execute(sql_poly, (order_wkt, route_wkt_4326, buffer_m))
        row = cur.fetchone()
    polygon_pct = min(100.0, round(float(row[0]), 2)) if row else 0.0
    uncovered_geojson = row[1] if row else None
    if isinstance(uncovered_geojson, str):
        uncovered_geojson = json.loads(uncovered_geojson)

    # Task coverage
    task_in_buffer = 0
    if task_points_4326:
        points_sql = " UNION ALL ".join(
            f"SELECT ST_SetSRID(ST_MakePoint({lng}, {lat}), 4326) AS geom"
            for lng, lat in task_points_4326
        )
        sql_tasks = f"""
            WITH route_buf AS (
                SELECT ST_Buffer(
                    ST_Transform(ST_GeomFromText(%s, 4326), {srid}),
                    %s
                ) AS geom
            ),
            pts AS ({points_sql})
            SELECT COUNT(*) FROM pts
            CROSS JOIN route_buf rb
            WHERE ST_DWithin(
                ST_Transform(pts.geom, {srid}),
                rb.geom,
                0
            )
        """
        with conn.cursor() as cur:
            cur.execute(sql_tasks, (route_wkt_4326, buffer_m))
            task_in_buffer = cur.fetchone()[0]

    task_pct = (
        round(100.0 * task_in_buffer / len(task_points_4326), 2)
        if task_points_4326
        else 100.0
    )
    return {
        "polygon_coverage_pct": polygon_pct,
        "task_coverage_pct": task_pct,
        "uncovered_geojson": uncovered_geojson,
        "tasks_total": len(task_points_4326),
        "tasks_covered": task_in_buffer,
    }


# ---------------------------------------------------------------------------
# OSRM orchestration
# ---------------------------------------------------------------------------

def _snap_waypoints(
    profile: str,
    waypoints: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Snap waypoints to the road network; drop those that can't snap."""
    from app.routing.osrm_client import nearest

    snapped: list[tuple[float, float]] = []
    for wp in waypoints:
        results = nearest(profile, wp, number=1)
        if results and results[0].distance < 500:
            snapped.append(results[0].location)
        else:
            logger.debug("Waypoint %s could not snap to %s network", wp, profile)
    return snapped


def _dedupe_nearby(
    coords: list[tuple[float, float]],
    min_dist_deg: float = 0.0003,  # ~30m at Moscow latitude
) -> list[tuple[float, float]]:
    """Remove near-duplicate coordinates."""
    if not coords:
        return []
    result = [coords[0]]
    for c in coords[1:]:
        if all(
            math.hypot(c[0] - r[0], c[1] - r[1]) >= min_dist_deg
            for r in result
        ):
            result.append(c)
    return result


def _build_route_via_trip(
    profile: str,
    waypoints: list[tuple[float, float]],
) -> tuple[list[tuple[float, float]], float, float, list[dict]]:
    """Order and route waypoints using OSRM Trip; returns (coords, distance, duration, segments)."""
    from app.routing.osrm_client import trip as osrm_trip, route as osrm_route

    if len(waypoints) <= 1:
        return [], 0.0, 0.0, []

    # If too many waypoints, chunk and chain
    all_coords: list[tuple[float, float]] = []
    total_dist = 0.0
    total_dur = 0.0
    segments: list[dict] = []

    chunks: list[list[tuple[float, float]]] = []
    for i in range(0, len(waypoints), OSRM_TRIP_CHUNK):
        chunk = waypoints[i : i + OSRM_TRIP_CHUNK]
        if len(chunk) < 2 and chunks:
            chunks[-1].extend(chunk)
        else:
            chunks.append(chunk)

    for idx, chunk in enumerate(chunks):
        if len(chunk) < 2:
            continue
        try:
            result = osrm_trip(profile, chunk, roundtrip=False, source="first")
        except Exception as exc:
            logger.warning("OSRM trip chunk %d failed: %s, falling back to route", idx, exc)
            try:
                result = osrm_route(profile, chunk)
            except Exception:
                continue

        if result.code != "Ok" or not result.geometry_coords:
            # fallback: direct route
            try:
                result = osrm_route(profile, chunk)
            except Exception:
                continue
            if result.code != "Ok":
                continue

        all_coords.extend(result.geometry_coords)
        total_dist += result.distance
        total_dur += result.duration
        segments.append({
            "profile": profile,
            "chunk_index": idx,
            "distance_m": result.distance,
            "duration_s": result.duration,
            "waypoint_count": len(chunk),
        })

    return all_coords, total_dist, total_dur, segments


def _coords_to_wkt(coords: list[tuple[float, float]]) -> str:
    """Convert coordinate list to WKT LINESTRING (4326)."""
    if len(coords) < 2:
        return "LINESTRING EMPTY"
    pts = ", ".join(f"{c[0]} {c[1]}" for c in coords)
    return f"LINESTRING({pts})"


def _multiline_wkt(coords: list[tuple[float, float]]) -> str:
    """WKT MULTILINESTRING from a single line."""
    if len(coords) < 2:
        return "MULTILINESTRING EMPTY"
    pts = ", ".join(f"{c[0]} {c[1]}" for c in coords)
    return f"MULTILINESTRING(({pts}))"


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_order_route(
    conn: PgConnection,
    order_key: str,
    *,
    start_lng_lat: tuple[float, float] | None = None,
    actor_login: str = "",
) -> dict[str, Any]:
    """Build, validate, save and return the order route context.

    Returns a dict suitable for the API response (route geometry, buffer,
    segments, coverage metrics, etc.).
    """
    settings = get_settings()
    buffer_m = settings.order_route_buffer_m
    grid_m = settings.order_route_grid_m

    # 1. Fetch order
    order = _fetch_order(conn, order_key)
    if order is None:
        raise OrderRouteError("Заказ не найден или без геометрии", status_code=404)

    order_wkt = order["order_wkt"]

    # 2. Fetch task points inside order
    task_points = _fetch_task_points(conn, order_wkt)
    logger.info("Order %s: %d task points inside polygon", order_key, len(task_points))

    # 3. Generate coverage grid
    grid_points = _generate_coverage_grid(conn, order_wkt, grid_m)
    logger.info("Order %s: %d coverage grid points", order_key, len(grid_points))

    # 4. Merge waypoints: start? + tasks + grid
    waypoints: list[tuple[float, float]] = []
    if start_lng_lat:
        waypoints.append(start_lng_lat)
    waypoints.extend(task_points)
    waypoints.extend(grid_points)
    waypoints = _dedupe_nearby(waypoints)

    if len(waypoints) > MAX_WAYPOINTS:
        waypoints = waypoints[:MAX_WAYPOINTS]
        logger.warning(
            "Order %s: truncated waypoints to %d", order_key, MAX_WAYPOINTS
        )

    if len(waypoints) < 2:
        raise OrderRouteError(
            "Недостаточно точек для построения маршрута (нужно ≥2)"
        )

    # 5. Snap to foot network
    snapped = _snap_waypoints("foot", waypoints)
    if len(snapped) < 2:
        raise OrderRouteError(
            "Не удалось привязать точки к пешеходной дорожной сети OSRM"
        )

    # 6. Build route via trip
    route_coords, distance, duration, segments = _build_route_via_trip("foot", snapped)
    if not route_coords:
        raise OrderRouteError("OSRM не смог построить маршрут")

    route_wkt_4326 = _coords_to_wkt(route_coords)

    # 7. Iterative refinement
    for iteration in range(MAX_REFINE_ITERATIONS):
        validation = _validate_route(
            conn, order_wkt, route_wkt_4326, task_points, buffer_m
        )
        if validation["polygon_coverage_pct"] >= 95.0:
            break

        gap_centroids = _uncovered_centroids(
            conn, order_wkt, route_wkt_4326, buffer_m, max_points=15
        )
        if not gap_centroids:
            break

        logger.info(
            "Order %s refine iteration %d: coverage=%.1f%%, adding %d gap waypoints",
            order_key,
            iteration + 1,
            validation["polygon_coverage_pct"],
            len(gap_centroids),
        )

        extra_snapped = _snap_waypoints("foot", gap_centroids)
        if not extra_snapped:
            # Try bike profile as fallback
            extra_snapped = _snap_waypoints("bike", gap_centroids)
        if not extra_snapped:
            break

        combined = snapped + extra_snapped
        combined = _dedupe_nearby(combined)
        if len(combined) > MAX_WAYPOINTS:
            combined = combined[:MAX_WAYPOINTS]

        new_coords, new_dist, new_dur, new_segs = _build_route_via_trip("foot", combined)
        if new_coords:
            route_coords = new_coords
            distance = new_dist
            duration = new_dur
            segments = new_segs
            route_wkt_4326 = _coords_to_wkt(route_coords)
            snapped = combined
    else:
        # Final validation after all iterations
        validation = _validate_route(
            conn, order_wkt, route_wkt_4326, task_points, buffer_m
        )

    # 8. Save to DB
    multiline_wkt = _multiline_wkt(route_coords)
    srid = _metric_srid()
    save_sql = f"""
        INSERT INTO crm.order_routes (
            order_key, route_geom, buffer_geom, segments,
            task_coverage_pct, polygon_coverage_pct, uncovered_geom,
            buffer_m, task_count, total_distance_m, total_duration_s,
            built_by, built_at, params
        ) VALUES (
            %s::uuid,
            ST_GeomFromText(%s, 4326),
            ST_Transform(
                ST_Buffer(
                    ST_Transform(ST_GeomFromText(%s, 4326), {srid}),
                    %s
                ),
                4326
            ),
            %s,
            %s, %s,
            CASE WHEN %s::text = 'null' THEN NULL
                 ELSE ST_GeomFromGeoJSON(%s)
            END,
            %s, %s, %s, %s,
            %s, %s, %s
        )
        ON CONFLICT (order_key) DO UPDATE SET
            route_geom = EXCLUDED.route_geom,
            buffer_geom = EXCLUDED.buffer_geom,
            segments = EXCLUDED.segments,
            task_coverage_pct = EXCLUDED.task_coverage_pct,
            polygon_coverage_pct = EXCLUDED.polygon_coverage_pct,
            uncovered_geom = EXCLUDED.uncovered_geom,
            buffer_m = EXCLUDED.buffer_m,
            task_count = EXCLUDED.task_count,
            total_distance_m = EXCLUDED.total_distance_m,
            total_duration_s = EXCLUDED.total_duration_s,
            built_by = EXCLUDED.built_by,
            built_at = EXCLUDED.built_at,
            params = EXCLUDED.params
    """
    uncovered_str = json.dumps(validation.get("uncovered_geojson")) if validation.get("uncovered_geojson") else "null"
    now = datetime.now(timezone.utc)
    params_json = {
        "buffer_m": buffer_m,
        "grid_m": grid_m,
        "start": list(start_lng_lat) if start_lng_lat else None,
        "refine_iterations": min(MAX_REFINE_ITERATIONS, 3),
    }

    with conn.cursor() as cur:
        cur.execute(save_sql, (
            order_key,
            multiline_wkt,
            multiline_wkt,
            buffer_m,
            Json(segments),
            validation["task_coverage_pct"],
            validation["polygon_coverage_pct"],
            uncovered_str,
            uncovered_str,
            buffer_m,
            len(task_points),
            distance,
            duration,
            actor_login or None,
            now,
            Json(params_json),
        ))
    conn.commit()

    # 9. Build response
    route_geojson: dict[str, Any] = {
        "type": "LineString",
        "coordinates": [list(c) for c in route_coords],
    }
    buffer_geojson = _fetch_saved_buffer_geojson(conn, order_key)

    return {
        "order_key": order_key,
        "order": {
            "task_number": order.get("task_number"),
            "rayon": order.get("rayon"),
            "geometry": order.get("geometry"),
        },
        "route_geometry": route_geojson,
        "buffer_geometry": buffer_geojson,
        "uncovered_geometry": validation.get("uncovered_geojson"),
        "segments": segments,
        "task_coverage_pct": validation["task_coverage_pct"],
        "polygon_coverage_pct": validation["polygon_coverage_pct"],
        "tasks_total": validation["tasks_total"],
        "tasks_covered": validation["tasks_covered"],
        "buffer_m": buffer_m,
        "total_distance_m": round(distance, 1),
        "total_duration_s": round(duration, 1),
        "built_by": actor_login or None,
        "built_at": now.isoformat(),
    }


# ---------------------------------------------------------------------------
# Fetch saved route
# ---------------------------------------------------------------------------

def fetch_saved_route(conn: PgConnection, order_key: str) -> dict[str, Any] | None:
    """Return the saved route context or None."""
    sql = """
        SELECT
            r.order_key::text,
            ST_AsGeoJSON(r.route_geom)::json AS route_geometry,
            ST_AsGeoJSON(r.buffer_geom)::json AS buffer_geometry,
            ST_AsGeoJSON(r.uncovered_geom)::json AS uncovered_geometry,
            r.segments,
            r.task_coverage_pct,
            r.polygon_coverage_pct,
            r.buffer_m,
            r.task_count,
            r.total_distance_m,
            r.total_duration_s,
            r.built_by,
            r.built_at,
            r.params,
            ta.task_number,
            ta.rayon,
            ST_AsGeoJSON(ta.geom)::json AS order_geometry
        FROM crm.order_routes r
        JOIN crm.tasks_area ta ON ta.key = r.order_key
        WHERE r.order_key = %s::uuid
        LIMIT 1
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, (order_key,))
        row = cur.fetchone()
    if not row:
        return None
    data = dict(row)
    # Normalise JSON fields
    for field in ("route_geometry", "buffer_geometry", "uncovered_geometry",
                  "order_geometry", "segments", "params"):
        val = data.get(field)
        if isinstance(val, str):
            data[field] = json.loads(val)
    if data.get("built_at"):
        data["built_at"] = data["built_at"].isoformat() if hasattr(data["built_at"], "isoformat") else str(data["built_at"])
    return {
        "order_key": str(data["order_key"]),
        "order": {
            "task_number": data.get("task_number"),
            "rayon": data.get("rayon"),
            "geometry": data.get("order_geometry"),
        },
        "route_geometry": data.get("route_geometry"),
        "buffer_geometry": data.get("buffer_geometry"),
        "uncovered_geometry": data.get("uncovered_geometry"),
        "segments": data.get("segments") or [],
        "task_coverage_pct": float(data["task_coverage_pct"]) if data.get("task_coverage_pct") is not None else None,
        "polygon_coverage_pct": float(data["polygon_coverage_pct"]) if data.get("polygon_coverage_pct") is not None else None,
        "tasks_total": data.get("task_count", 0),
        "tasks_covered": None,  # not stored separately
        "buffer_m": float(data["buffer_m"]) if data.get("buffer_m") is not None else 100.0,
        "total_distance_m": float(data["total_distance_m"]) if data.get("total_distance_m") is not None else None,
        "total_duration_s": float(data["total_duration_s"]) if data.get("total_duration_s") is not None else None,
        "built_by": data.get("built_by"),
        "built_at": data.get("built_at"),
    }


def _fetch_saved_buffer_geojson(conn: PgConnection, order_key: str) -> dict | None:
    sql = """
        SELECT ST_AsGeoJSON(buffer_geom)::json
        FROM crm.order_routes
        WHERE order_key = %s::uuid
        LIMIT 1
    """
    with conn.cursor() as cur:
        cur.execute(sql, (order_key,))
        row = cur.fetchone()
    if not row or not row[0]:
        return None
    val = row[0]
    if isinstance(val, str):
        return json.loads(val)
    return val


def fetch_route_geojson_export(conn: PgConnection, order_key: str) -> dict[str, Any] | None:
    """Return a GeoJSON FeatureCollection with route, buffer, and uncovered polygons."""
    saved = fetch_saved_route(conn, order_key)
    if not saved:
        return None
    features: list[dict] = []
    if saved.get("route_geometry"):
        features.append({
            "type": "Feature",
            "properties": {
                "layer": "route",
                "total_distance_m": saved.get("total_distance_m"),
                "total_duration_s": saved.get("total_duration_s"),
            },
            "geometry": saved["route_geometry"],
        })
    if saved.get("buffer_geometry"):
        features.append({
            "type": "Feature",
            "properties": {"layer": "buffer", "buffer_m": saved.get("buffer_m")},
            "geometry": saved["buffer_geometry"],
        })
    if saved.get("order", {}).get("geometry"):
        features.append({
            "type": "Feature",
            "properties": {"layer": "order_polygon"},
            "geometry": saved["order"]["geometry"],
        })
    if saved.get("uncovered_geometry"):
        features.append({
            "type": "Feature",
            "properties": {"layer": "uncovered"},
            "geometry": saved["uncovered_geometry"],
        })
    return {
        "type": "FeatureCollection",
        "features": features,
    }
