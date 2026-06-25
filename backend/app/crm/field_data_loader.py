"""Load «Полевые данные» tasks from crm.tasks + mggt_field.reports."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

from app.config import crm_task_store_config, crm_tasks_config
from app.crm.store import FIELD_DATA_SUBGROUP, TASK_ID_COLUMNS, fetch_snapshot_task_keys
from app.layers.geojson import fetch_district_wkt

FIELD_DATA_LAYER_KEY = "field_data"
FIELD_DATA_LAYER_NAME = "Полевые данные"

_REPORT_SKIP_COLUMNS = frozenset({"point", "tasks_key", "geom", "geometry"})


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


def _field_data_mapping(store_cfg: dict[str, Any]) -> dict[str, Any]:
    return store_cfg.get("subgroups", {}).get(FIELD_DATA_SUBGROUP, {})


def _reports_qualified_table(mapping: dict[str, Any]) -> str:
    schema = mapping.get("reports_schema", "mggt_field")
    table = mapping.get("reports_table", "reports")
    return f'"{schema}"."{table}"'


def _serialize_report_value(value: Any) -> Any:
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


def report_row_to_attributes(row: dict[str, Any]) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    for key, value in row.items():
        if key in _REPORT_SKIP_COLUMNS:
            continue
        if key.startswith("_"):
            continue
        serialized = _serialize_report_value(value)
        if serialized is not None:
            attrs[key] = serialized
    return attrs


def fetch_field_report_row(
    conn: PgConnection,
    task_key: str,
    store_cfg: dict[str, Any],
) -> dict[str, Any] | None:
    mapping = _field_data_mapping(store_cfg)
    if mapping.get("source") != "field_data":
        return None

    reports_table = _reports_qualified_table(mapping)
    tasks_key_col = mapping.get("reports_tasks_key", "tasks_key")
    geom_col = mapping.get("reports_geometry", "point")

    query = f"""
        SELECT r.*,
               ST_AsGeoJSON(ST_Transform(r."{geom_col}", 4326))::json AS _geometry
        FROM {reports_table} r
        WHERE r."{tasks_key_col}" = %s::uuid
          AND r."{geom_col}" IS NOT NULL
        LIMIT 1
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (task_key,))
        row = cur.fetchone()
    return dict(row) if row else None


def mark_discovered_field_data_tasks(
    conn: PgConnection,
    store_cfg: dict[str, Any],
) -> int:
    """Проставить is_field_data=true для задач, подходящих под критерий «Полевые данные».

    Критерий обнаружения (один раз, флаг не сбрасывается):
    - field_observed = true
    - все TASK_ID_COLUMNS = NULL
    - есть запись в mggt_field.reports (tasks_key) с ненулевой геометрией
    """
    mapping = _field_data_mapping(store_cfg)
    if mapping.get("source") != "field_data":
        return 0

    tasks_schema, tasks_table = store_cfg.get("schema", "crm"), store_cfg.get("table", "tasks")
    reports_table = _reports_qualified_table(mapping)
    tasks_key_col = mapping.get("reports_tasks_key", "tasks_key")
    geom_col = mapping.get("reports_geometry", "point")
    null_checks = " AND ".join(f't."{col}" IS NULL' for col in TASK_ID_COLUMNS)

    query = f"""
        UPDATE "{tasks_schema}"."{tasks_table}" t
        SET is_field_data = true
        FROM {reports_table} r
        WHERE r."{tasks_key_col}" = t.key
          AND COALESCE(t.is_field_data, false) IS NOT TRUE
          AND t.field_observed IS TRUE
          AND {null_checks}
          AND r."{geom_col}" IS NOT NULL
    """
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            updated = cur.rowcount
        conn.commit()
        return updated
    except Exception:
        conn.rollback()
        raise


def _row_to_task_feature(
    row: dict[str, Any],
    report_attrs: dict[str, Any],
    geometry: dict[str, Any] | None,
):
    from app.crm.collector import TaskFeature

    attrs = dict(report_attrs)
    attrs["field_observed"] = bool(row.get("field_observed"))
    attrs["is_field_data"] = True
    for col in ("oati_id", "earthwork_id", "localwork_id", "avr_mos_id", "sps", "kgs", "station_avr"):
        value = row.get(col)
        if value is not None and str(value).strip():
            attrs[col] = str(value).strip()

    return TaskFeature(
        layer_name=FIELD_DATA_LAYER_NAME,
        layer_key=FIELD_DATA_LAYER_KEY,
        attributes=attrs,
        geometry=geometry,
        task_key=str(row["key"]),
    )


def collect_field_data_tasks(
    conn: PgConnection,
    rayon: str,
    apply_date_filter: bool,
):
    from app.crm.collector import TaskFeature

    del apply_date_filter  # date filter — when report date field is known

    store_cfg = crm_task_store_config()
    if not store_cfg:
        return [], []

    mapping = _field_data_mapping(store_cfg)
    if mapping.get("source") != "field_data":
        return [], []

    try:
        mark_discovered_field_data_tasks(conn, store_cfg)
    except Exception as exc:
        return [], [f"{FIELD_DATA_LAYER_NAME}: не удалось обновить is_field_data: {exc}"]

    district_wkt, metric_srid, errors = _district_context(conn, rayon)
    if not district_wkt:
        return [], errors

    tasks_schema, tasks_table = store_cfg.get("schema", "crm"), store_cfg.get("table", "tasks")
    reports_table = _reports_qualified_table(mapping)
    tasks_key_col = mapping.get("reports_tasks_key", "tasks_key")
    geom_col = mapping.get("reports_geometry", "point")

    query = f"""
        SELECT t.key, t.type, t.field_observed, t.is_field_data,
               t.oati_id, t.earthwork_id, t.localwork_id, t.avr_mos_id,
               t.sps, t.kgs, t.station_avr,
               ST_AsGeoJSON(ST_Transform(r."{geom_col}", 4326))::json AS geometry,
               row_to_json(r)::json AS report_json
        FROM "{tasks_schema}"."{tasks_table}" t
        INNER JOIN {reports_table} r ON r."{tasks_key_col}" = t.key
        WHERE t.is_field_data IS TRUE
          AND t.field_observed IS TRUE
          AND r."{geom_col}" IS NOT NULL
          AND ST_Intersects(
              ST_Transform(r."{geom_col}", {metric_srid}),
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

                report_raw = row.get("report_json") or {}
                if isinstance(report_raw, str):
                    report_raw = json.loads(report_raw)
                report_attrs = report_row_to_attributes(dict(report_raw))

                features.append(_row_to_task_feature(row, report_attrs, geometry))
    except Exception as exc:
        errors = list(errors)
        errors.append(f"{FIELD_DATA_LAYER_NAME}: {exc}")
        return [], errors

    return features, errors
