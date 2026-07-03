"""Load order tracks from mggt_field.tracks."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

from app.config import crm_tasks_config, order_tracks_config
from app.layers.geojson import fetch_district_wkt

_TRACK_SKIP_COLUMNS = frozenset({"geom", "geometry"})


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


def _serialize_track_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (dict, list)):
        return value
    return value


def track_row_to_attributes(row: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    id_col = cfg.get("id_column", "id")
    geom_col = cfg.get("geometry_column", "geom")
    skip = _TRACK_SKIP_COLUMNS | {id_col, geom_col}
    attrs: dict[str, Any] = {}
    for key, value in row.items():
        if key in skip or key.startswith("_"):
            continue
        serialized = _serialize_track_value(value)
        if serialized is not None:
            attrs[key] = serialized
    return attrs


def fetch_order_tracks(
    conn: PgConnection,
    rayon: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    cfg = order_tracks_config()
    schema = cfg.get("schema", "mggt_field")
    table = cfg.get("table", "tracks")
    id_col = cfg.get("id_column", "id")
    geom_col = cfg.get("geometry_column", "geom")

    district_wkt, metric_srid, errors = _district_context(conn, rayon)
    if not district_wkt:
        return [], errors

    track_geom = f'ST_Transform(t."{geom_col}", {metric_srid})'
    clipped_geom = f"""
        ST_LineMerge(
            ST_CollectionExtract(
                ST_Intersection({track_geom}, district.geom),
                2
            )
        )
    """
    clipped_geojson = f"""
        ST_AsGeoJSON(
            ST_Transform({clipped_geom}, 4326)
        )::json
    """

    query = f"""
        WITH district AS (
            SELECT ST_GeomFromText(%s, {metric_srid}) AS geom
        )
        SELECT t."{id_col}"::text AS track_id,
               {clipped_geojson} AS geometry,
               row_to_json(t)::json AS row_json
        FROM "{schema}"."{table}" t
        CROSS JOIN district
        WHERE t."{geom_col}" IS NOT NULL
          AND ST_Intersects({track_geom}, district.geom)
          AND NOT ST_IsEmpty({clipped_geom})
        ORDER BY t.created_at DESC NULLS LAST
        LIMIT 5000
    """

    tracks: list[dict[str, Any]] = []
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
                attrs = track_row_to_attributes(dict(row_raw), cfg)

                tracks.append(
                    {
                        "id": str(row["track_id"]),
                        "attributes": attrs,
                        "geometry": geometry,
                    }
                )
    except Exception as exc:
        errors = list(errors)
        errors.append(f"Треки заказов: {exc}")
        return [], errors

    return tracks, errors
