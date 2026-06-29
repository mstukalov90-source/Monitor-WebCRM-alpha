"""Load «Задачи из камерального анализа» from crm.tasks + crm.office_task_points."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

from app.config import crm_task_store_config, crm_tasks_config
from app.crm.store import OFFICE_DATA_SUBGROUP, fetch_snapshot_task_keys
from app.layers.geojson import fetch_district_wkt

OFFICE_DATA_LAYER_KEY = "office_data"
OFFICE_DATA_LAYER_NAME = "Задачи из камерального анализа"


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


def _office_data_mapping(store_cfg: dict[str, Any]) -> dict[str, Any]:
    return store_cfg.get("subgroups", {}).get(OFFICE_DATA_SUBGROUP, {})


def _points_qualified_table(mapping: dict[str, Any]) -> str:
    schema = mapping.get("points_schema", "crm")
    table = mapping.get("points_table", "office_task_points")
    return f'"{schema}"."{table}"'


def fetch_office_task_point(
    conn: PgConnection,
    task_key: str,
    store_cfg: dict[str, Any],
) -> dict[str, Any] | None:
    mapping = _office_data_mapping(store_cfg)
    if mapping.get("source") != "office_data":
        return None

    points_table = _points_qualified_table(mapping)
    geom_col = mapping.get("points_geometry", "point")

    query = f"""
        SELECT p.task_key,
               p.created_at,
               ST_AsGeoJSON(p."{geom_col}")::json AS _geometry
        FROM {points_table} p
        WHERE p.task_key = %s::uuid
          AND p."{geom_col}" IS NOT NULL
        LIMIT 1
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (task_key,))
        row = cur.fetchone()
    return dict(row) if row else None


def _serialize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _row_to_task_feature(row: dict[str, Any], geometry: dict[str, Any] | None):
    from app.crm.collector import TaskFeature

    attrs: dict[str, Any] = {
        "is_office_task": True,
        "created_at": _serialize_value(row.get("created_at")),
    }
    for col in ("oati_id", "earthwork_id", "localwork_id", "avr_mos_id", "sps", "kgs", "station_avr"):
        value = row.get(col)
        if value is not None and str(value).strip():
            attrs[col] = str(value).strip()

    return TaskFeature(
        layer_name=OFFICE_DATA_LAYER_NAME,
        layer_key=OFFICE_DATA_LAYER_KEY,
        attributes=attrs,
        geometry=geometry,
        task_key=str(row["key"]),
    )


def collect_office_data_tasks(
    conn: PgConnection,
    rayon: str,
    apply_date_filter: bool,
):
    from app.crm.collector import TaskFeature

    del apply_date_filter

    store_cfg = crm_task_store_config()
    if not store_cfg:
        return [], []

    mapping = _office_data_mapping(store_cfg)
    if mapping.get("source") != "office_data":
        return [], []

    district_wkt, metric_srid, errors = _district_context(conn, rayon)
    if not district_wkt:
        return [], errors

    tasks_schema, tasks_table = store_cfg.get("schema", "crm"), store_cfg.get("table", "tasks")
    points_table = _points_qualified_table(mapping)
    geom_col = mapping.get("points_geometry", "point")

    query = f"""
        SELECT t.key, t.type, t.is_office_task,
               t.oati_id, t.earthwork_id, t.localwork_id, t.avr_mos_id,
               t.sps, t.kgs, t.station_avr,
               p.created_at,
               ST_AsGeoJSON(p."{geom_col}")::json AS geometry
        FROM "{tasks_schema}"."{tasks_table}" t
        INNER JOIN {points_table} p ON p.task_key = t.key
        WHERE t.is_office_task IS TRUE
          AND p."{geom_col}" IS NOT NULL
          AND ST_Intersects(
              ST_Transform(p."{geom_col}", {metric_srid}),
              ST_GeomFromText(%s, {metric_srid})
          )
    """

    snapshot_keys = fetch_snapshot_task_keys(conn, store_cfg)
    features: list[TaskFeature] = []

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (district_wkt,))
            for row in cur.fetchall():
                task_key = str(row["key"])
                if task_key in snapshot_keys:
                    continue
                geometry = row.get("geometry")
                if isinstance(geometry, str):
                    geometry = json.loads(geometry)
                features.append(_row_to_task_feature(row, geometry))
    except Exception as exc:
        errors = list(errors)
        errors.append(f"{OFFICE_DATA_LAYER_NAME}: {exc}")
        return [], errors

    return features, errors
