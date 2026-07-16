"""Load employee real-time locations from mggt_field.track_real_time."""

from __future__ import annotations

import json
from typing import Any

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

from app.config import crm_tasks_config, employee_locations_config
from app.layers.geojson import fetch_district_wkt


def _table_config() -> tuple[str, str, str, str, list[str]]:
    cfg = employee_locations_config()
    schema = cfg.get("schema", "mggt_field")
    table = cfg.get("table", "track_real_time")
    id_col = cfg.get("id_column", "user")
    geom_col = cfg.get("geometry_column", "geom")
    display_columns = cfg.get("display_columns", ["user"])
    return schema, table, id_col, geom_col, display_columns


def _rows_to_locations(
    rows: list[dict[str, Any]],
    display_columns: list[str],
) -> list[dict[str, Any]]:
    locations: list[dict[str, Any]] = []
    for row in rows:
        geometry = row.get("geometry")
        if isinstance(geometry, str):
            geometry = json.loads(geometry)
        if not geometry:
            continue

        row_raw = row.get("row_json") or {}
        if isinstance(row_raw, str):
            row_raw = json.loads(row_raw)
        row_dict = dict(row_raw)

        attrs: dict[str, Any] = {}
        for col in display_columns:
            if col in row_dict and row_dict[col] is not None:
                attrs[col] = row_dict[col]

        locations.append(
            {
                "id": str(row["location_id"]),
                "attributes": attrs,
                "geometry": geometry,
            }
        )
    return locations


def _district_context(
    conn: PgConnection,
    rayon: str,
) -> tuple[str | None, int, list[str]]:
    cfg = crm_tasks_config()
    metric_crs = cfg.get("metric_crs", "EPSG:32637")
    metric_srid = int(metric_crs.split(":")[-1]) if ":" in metric_crs else 32637
    district_cfg = cfg.get("district_filter", {})
    district_wkt = fetch_district_wkt(
        conn,
        rayon,
        "odh_export",
        "hood",
        district_cfg.get("field", "rayon"),
        metric_srid,
    )
    errors: list[str] = []
    if not district_wkt:
        errors.append(f"District polygon not found for «{rayon}»")
    return district_wkt, metric_srid, errors


def fetch_all_employee_locations(
    conn: PgConnection,
) -> tuple[list[dict[str, Any]], list[str]]:
    schema, table, id_col, geom_col, display_columns = _table_config()
    geojson = f'ST_AsGeoJSON(t."{geom_col}")::json'

    query = f"""
        SELECT DISTINCT ON (t."{id_col}")
               t."{id_col}"::text AS location_id,
               {geojson} AS geometry,
               row_to_json(t)::json AS row_json
        FROM "{schema}"."{table}" t
        WHERE t."{geom_col}" IS NOT NULL
        ORDER BY t."{id_col}", t.time DESC NULLS LAST
        LIMIT 5000
    """

    errors: list[str] = []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query)
            locations = _rows_to_locations(cur.fetchall(), display_columns)
    except Exception as exc:
        errors.append(f"Местоположение сотрудников: {exc}")
        return [], errors

    return locations, errors


def fetch_employee_locations(
    conn: PgConnection,
    rayon: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    schema, table, id_col, geom_col, display_columns = _table_config()

    district_wkt, metric_srid, errors = _district_context(conn, rayon)
    if not district_wkt:
        return [], errors

    point_geom = f'ST_Transform(t."{geom_col}", {metric_srid})'
    geojson = f'ST_AsGeoJSON(t."{geom_col}")::json'

    query = f"""
        WITH district AS (
            SELECT ST_GeomFromText(%s, {metric_srid}) AS geom
        )
        SELECT DISTINCT ON (t."{id_col}")
               t."{id_col}"::text AS location_id,
               {geojson} AS geometry,
               row_to_json(t)::json AS row_json
        FROM "{schema}"."{table}" t
        CROSS JOIN district
        WHERE t."{geom_col}" IS NOT NULL
          AND ST_Intersects({point_geom}, district.geom)
        ORDER BY t."{id_col}", t.time DESC NULLS LAST
        LIMIT 5000
    """

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (district_wkt,))
            locations = _rows_to_locations(cur.fetchall(), display_columns)
    except Exception as exc:
        errors = list(errors)
        errors.append(f"Местоположение сотрудников: {exc}")
        return [], errors

    return locations, errors
