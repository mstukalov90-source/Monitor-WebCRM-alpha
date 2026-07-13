"""Load employee real-time locations from mggt_field.track_real_time."""

from __future__ import annotations

import json
from typing import Any

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

from app.config import crm_tasks_config, employee_locations_config
from app.layers.geojson import fetch_district_wkt


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


def fetch_employee_locations(
    conn: PgConnection,
    rayon: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    cfg = employee_locations_config()
    schema = cfg.get("schema", "mggt_field")
    table = cfg.get("table", "track_real_time")
    id_col = cfg.get("id_column", "user")
    geom_col = cfg.get("geometry_column", "geom")
    display_columns = cfg.get("display_columns", ["user"])

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

    locations: list[dict[str, Any]] = []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (district_wkt,))
            for row in cur.fetchall():
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
    except Exception as exc:
        errors = list(errors)
        errors.append(f"Местоположение сотрудников: {exc}")
        return [], errors

    return locations, errors
