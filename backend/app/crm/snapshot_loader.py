"""Загрузка задач из таблиц-снимков (tasks_field, tasks_done_*)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

from app.config import crm_task_store_config, crm_tasks_config
from app.crm.collector import (
    TaskFeature,
    TaskGroup,
    TaskResult,
    TaskSubgroup,
    _date_filter_range,
    task_result_to_dict,
)
from app.crm.link_resolver import find_subgroup_cfg
from app.crm.field_data_loader import (
    FIELD_DATA_LAYER_KEY,
    FIELD_DATA_LAYER_NAME,
    fetch_field_report_row,
    report_row_to_attributes,
)
from app.crm.office_data_loader import (
    OFFICE_DATA_LAYER_KEY,
    OFFICE_DATA_LAYER_NAME,
    fetch_office_task_point,
)
from app.crm.store import (
    FIELD_DATA_SUBGROUP,
    OFFICE_DATA_SUBGROUP,
    TASK_ID_COLUMNS,
    TaskRecord,
    _find_subgroup_for_record,
    enrich_task_result_field_observed,
)
from app.layers.geojson import fetch_district_wkt, geometry_in_district, lookup_feature
from app.layers.registry import get_registry

SNAPSHOT_SOURCES = {
    "field": ("field_table", "tasks_field"),
    "done_legal": ("done_legal_table", "tasks_done_legal"),
    "done_illegal": ("done_illegal_table", "tasks_done_illegal"),
    "clear": ("clear_table", "tasks_clear"),
}


@dataclass
class SnapshotRow:
    snapshot_key: str
    task_key: str
    sent_at: Optional[str]
    record: TaskRecord
    subgroup_name: str
    group_name: str
    executor: Optional[str] = None
    office_comment: Optional[str] = None


def _snapshot_table_ref(store_cfg: dict, config_key: str, default_table: str) -> tuple[str, str]:
    schema = store_cfg.get("schema", "crm")
    table = store_cfg.get(config_key, default_table)
    return schema, table


def _find_group_name(subgroup_name: str, crm_cfg: dict[str, Any]) -> str:
    for group_cfg in crm_cfg.get("groups", []):
        for sub_cfg in group_cfg.get("subgroups", []):
            if sub_cfg.get("name") == subgroup_name:
                return group_cfg.get("name", "")
    return ""


def _apply_snapshot_metadata(attrs: dict[str, Any], snap: SnapshotRow) -> None:
    if snap.executor:
        attrs["executor"] = snap.executor
    if snap.sent_at:
        attrs["_sent_at"] = snap.sent_at
    if snap.office_comment and str(snap.office_comment).strip():
        attrs["office_comment"] = str(snap.office_comment).strip()


def _row_to_snapshot_row(
    row: dict[str, Any],
    store_cfg: dict[str, Any],
    crm_cfg: dict[str, Any],
    *,
    include_executor: bool,
) -> SnapshotRow | None:
    record = TaskRecord(
        key=str(row["task_key"]),
        type=row["type"] or "",
        photo_uuid=row.get("photo_uuid"),
        photo_lens=row.get("photo_lens"),
        ogh_id=row.get("ogh_id"),
        oati_id=row.get("oati_id"),
        earthwork_id=row.get("earthwork_id"),
        localwork_id=row.get("localwork_id"),
        avr_mos_id=row.get("avr_mos_id"),
        sps=row.get("sps"),
        kgs=row.get("kgs"),
        station_avr=row.get("station_avr"),
        is_field_data=bool(row.get("is_field_data")) if row.get("is_field_data") is not None else None,
        is_office_task=bool(row.get("is_office_task")) if row.get("is_office_task") is not None else None,
    )
    resolved = _find_subgroup_for_record(record, store_cfg)
    if resolved is None:
        return None
    subgroup_name, _, _ = resolved
    group_name = row["type"] or _find_group_name(subgroup_name, crm_cfg)
    sent_at = row.get("sent_at")
    sent_str = sent_at.isoformat() if isinstance(sent_at, datetime) else str(sent_at or "")
    return SnapshotRow(
        snapshot_key=str(row["key"]),
        task_key=str(row["task_key"]),
        sent_at=sent_str or None,
        record=record,
        subgroup_name=subgroup_name,
        group_name=group_name,
        executor=row.get("executor") if include_executor else None,
        office_comment=row.get("office_comment") if include_executor else None,
    )


def _snapshot_select_columns(table: str) -> list[str]:
    columns = (
        ["key", "task_key", "sent_at", "type"]
        + list(TASK_ID_COLUMNS)
        + ["sps", "kgs", "station_avr", "is_field_data", "is_office_task"]
    )
    if table == "tasks_field":
        columns.append("executor")
        columns.append("office_comment")
    return columns


def fetch_snapshot_rows(
    conn: PgConnection,
    store_cfg: dict[str, Any],
    config_key: str,
    default_table: str,
    *,
    field_executor_login: str | None = None,
) -> list[SnapshotRow]:
    schema, table = _snapshot_table_ref(store_cfg, config_key, default_table)
    crm_cfg = crm_tasks_config()
    include_executor = table == "tasks_field"
    if include_executor:
        from app.crm.executor import ensure_executor_column
        from app.crm.store import ensure_office_comment_column

        ensure_executor_column(conn, schema, table)
        ensure_office_comment_column(conn, schema, table)
    col_list = ", ".join(f'"{c}"' for c in _snapshot_select_columns(table))

    filters: list[str] = []
    params: list[Any] = []
    if field_executor_login is not None and table == "tasks_field":
        from app.crm.executor import ensure_executor_column

        ensure_executor_column(conn, schema, table)
        filters.append("(executor IS NULL OR executor = %s)")
        params.append(field_executor_login)

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    query = f'SELECT {col_list} FROM "{schema}"."{table}" {where} ORDER BY sent_at DESC'

    rows: list[SnapshotRow] = []
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        for row in cur.fetchall():
            snap = _row_to_snapshot_row(row, store_cfg, crm_cfg, include_executor=include_executor)
            if snap is not None:
                rows.append(snap)
    return rows


def fetch_snapshot_rows_by_keys(
    conn: PgConnection,
    store_cfg: dict[str, Any],
    config_key: str,
    default_table: str,
    snapshot_keys: list[str],
) -> list[SnapshotRow]:
    if not snapshot_keys:
        return []
    schema, table = _snapshot_table_ref(store_cfg, config_key, default_table)
    crm_cfg = crm_tasks_config()
    include_executor = table == "tasks_field"
    if include_executor:
        from app.crm.executor import ensure_executor_column
        from app.crm.store import ensure_office_comment_column

        ensure_executor_column(conn, schema, table)
        ensure_office_comment_column(conn, schema, table)
    col_list = ", ".join(f'"{c}"' for c in _snapshot_select_columns(table))
    query = f'SELECT {col_list} FROM "{schema}"."{table}" WHERE key = ANY(%s::uuid[])'

    rows: list[SnapshotRow] = []
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (snapshot_keys,))
        for row in cur.fetchall():
            snap = _row_to_snapshot_row(row, store_cfg, crm_cfg, include_executor=include_executor)
            if snap is not None:
                rows.append(snap)
    return rows


def _subgroup_cfg(subgroup_name: str) -> Optional[dict[str, Any]]:
    for group_cfg in crm_tasks_config().get("groups", []):
        for sub_cfg in group_cfg.get("subgroups", []):
            if sub_cfg.get("name") == subgroup_name:
                return sub_cfg
    return None


def _field_data_snapshot_to_feature(
    conn: PgConnection,
    snap: SnapshotRow,
    store_cfg: dict[str, Any],
    district_wkt: str,
    metric_srid: int,
) -> Optional[TaskFeature]:
    import json

    report_row = fetch_field_report_row(conn, snap.task_key, store_cfg)
    if not report_row:
        return None

    geometry = report_row.pop("_geometry", None)
    if isinstance(geometry, str):
        geometry = json.loads(geometry)
    if not geometry:
        return None

    from app.layers.geojson import geometry_in_district

    if not geometry_in_district(conn, geometry, district_wkt, metric_srid):
        return None

    attrs = report_row_to_attributes(report_row)
    attrs["_task_key"] = snap.task_key
    attrs["_snapshot_key"] = snap.snapshot_key
    attrs["field_observed"] = bool(snap.record.field_observed)
    attrs["is_field_data"] = True
    _apply_snapshot_metadata(attrs, snap)
    for col in ("oati_id", "earthwork_id", "localwork_id", "avr_mos_id", "sps", "kgs", "station_avr"):
        value = getattr(snap.record, col, None)
        if value is not None and str(value).strip():
            attrs[col] = str(value).strip()

    return TaskFeature(
        layer_name=FIELD_DATA_LAYER_NAME,
        layer_key=FIELD_DATA_LAYER_KEY,
        attributes=attrs,
        geometry=geometry,
        task_key=snap.task_key,
        sent_at=snap.sent_at,
    )


def _office_data_snapshot_to_feature(
    conn: PgConnection,
    snap: SnapshotRow,
    store_cfg: dict[str, Any],
    district_wkt: str,
    metric_srid: int,
) -> Optional[TaskFeature]:
    import json

    point_row = fetch_office_task_point(conn, snap.task_key, store_cfg)
    if not point_row:
        return None

    geometry = point_row.pop("_geometry", None)
    if isinstance(geometry, str):
        geometry = json.loads(geometry)
    if not geometry:
        return None

    from app.layers.geojson import geometry_in_district

    if not geometry_in_district(conn, geometry, district_wkt, metric_srid):
        return None

    attrs: dict[str, Any] = {
        "_task_key": snap.task_key,
        "_snapshot_key": snap.snapshot_key,
        "is_office_task": True,
        "created_at": point_row.get("created_at").isoformat()
        if point_row.get("created_at") is not None
        else None,
    }
    _apply_snapshot_metadata(attrs, snap)
    for col in ("oati_id", "earthwork_id", "localwork_id", "avr_mos_id", "sps", "kgs", "station_avr"):
        value = getattr(snap.record, col, None)
        if value is not None and str(value).strip():
            attrs[col] = str(value).strip()

    return TaskFeature(
        layer_name=OFFICE_DATA_LAYER_NAME,
        layer_key=OFFICE_DATA_LAYER_KEY,
        attributes=attrs,
        geometry=geometry,
        task_key=snap.task_key,
        sent_at=snap.sent_at,
    )


def snapshot_row_to_feature(
    conn: PgConnection,
    snap: SnapshotRow,
    store_cfg: dict[str, Any],
    district_wkt: str,
    metric_srid: int,
) -> Optional[TaskFeature]:
    if snap.record.is_field_data or snap.subgroup_name == FIELD_DATA_SUBGROUP:
        return _field_data_snapshot_to_feature(
            conn, snap, store_cfg, district_wkt, metric_srid
        )
    if snap.record.is_office_task or snap.subgroup_name == OFFICE_DATA_SUBGROUP:
        return _office_data_snapshot_to_feature(
            conn, snap, store_cfg, district_wkt, metric_srid
        )

    registry = get_registry()
    mapping = store_cfg.get("subgroups", {}).get(snap.subgroup_name)
    if not mapping:
        return None

    source_field = mapping.get("source_field")
    task_column = mapping.get("task_column")
    business_id = getattr(snap.record, task_column, None)
    if not source_field or not business_id:
        return None

    sub_cfg = _subgroup_cfg(snap.subgroup_name)
    if sub_cfg is None:
        return None

    layers, _ = registry.resolve_subgroup_layers(
        sub_cfg.get("layers", []),
        sub_cfg.get("groups", []),
    )
    from app.crm.store import parse_scoped_business_id

    scoped = bool(mapping.get("scoped_geometry_id"))
    prefix, raw_business_id = parse_scoped_business_id(str(business_id))
    feature_data = None
    for layer in layers:
        if scoped and prefix and layer.geometry_type != prefix:
            continue
        lookup_id = raw_business_id if scoped else str(business_id)
        feature_data = lookup_feature(conn, layer, source_field, lookup_id)
        if feature_data:
            break
    if not feature_data or not feature_data.get("geometry"):
        return None

    geom = feature_data["geometry"]
    if not geometry_in_district(conn, geom, district_wkt, metric_srid):
        return None

    attrs = dict(feature_data.get("attributes") or {})
    attrs["_task_key"] = snap.task_key
    attrs["_snapshot_key"] = snap.snapshot_key
    _apply_snapshot_metadata(attrs, snap)

    return TaskFeature(
        layer_name=feature_data.get("layer_name", ""),
        layer_key=feature_data.get("layer_key", ""),
        attributes=attrs,
        geometry=geom,
        task_key=snap.task_key,
        sent_at=snap.sent_at,
    )


def collect_snapshot_tasks(
    conn: PgConnection,
    rayon: str,
    source: str,
    *,
    field_executor_login: str | None = None,
) -> TaskResult:
    if source not in SNAPSHOT_SOURCES:
        raise ValueError(f"Unknown snapshot source: {source}")

    store_cfg = crm_task_store_config()
    crm_cfg = crm_tasks_config()
    config_key, default_table = SNAPSHOT_SOURCES[source]

    lookback_days = int(crm_cfg.get("date_lookback_days", 3))
    date_from, date_to = _date_filter_range(lookback_days)
    metric_crs = crm_cfg.get("metric_crs", "EPSG:32637")
    metric_srid = int(metric_crs.split(":")[-1]) if ":" in metric_crs else 32637

    district_wkt = fetch_district_wkt(conn, rayon, metric_srid=metric_srid)
    if not district_wkt:
        return TaskResult(
            district_name=rayon,
            filter_date_from=date_from,
            filter_date_to=date_to,
            apply_date_filter=False,
            errors=[f"District polygon not found for «{rayon}»"],
        )

    executor_filter = field_executor_login if source == "field" else None
    snapshot_rows = fetch_snapshot_rows(
        conn,
        store_cfg,
        config_key,
        default_table,
        field_executor_login=executor_filter,
    )

    groups_map: dict[str, dict[str, list[TaskFeature]]] = {}
    for snap in snapshot_rows:
        feat = snapshot_row_to_feature(conn, snap, store_cfg, district_wkt, metric_srid)
        if feat is None:
            continue
        groups_map.setdefault(snap.group_name, {}).setdefault(snap.subgroup_name, []).append(feat)

    result = TaskResult(
        district_name=rayon,
        filter_date_from=date_from,
        filter_date_to=date_to,
        apply_date_filter=False,
    )

    for group_cfg in crm_cfg.get("groups", []):
        group_name = group_cfg.get("name", "")
        sub_map = groups_map.get(group_name, {})
        if not sub_map:
            continue
        group = TaskGroup(name=group_name)
        for sub_cfg in group_cfg.get("subgroups", []):
            sub_name = sub_cfg.get("name", "")
            features = sub_map.get(sub_name, [])
            if features:
                group.subgroups.append(TaskSubgroup(name=sub_name, features=features))
        if group.subgroups:
            result.groups.append(group)

    store_cfg = crm_task_store_config()
    if store_cfg:
        enrich_task_result_field_observed(result, conn, store_cfg)

    return result


def snapshot_result_to_dict(result: TaskResult, source: str) -> dict[str, Any]:
    data = task_result_to_dict(result)
    data["task_source"] = source
    return data
