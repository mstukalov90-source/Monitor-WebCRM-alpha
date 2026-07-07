"""Load ETL-synced photo tasks (genplan + lens) from crm.tasks JOIN."""

from __future__ import annotations

from typing import Any

from psycopg2.extensions import connection as PgConnection

from app.config import crm_task_store_config, crm_tasks_config
from app.crm.link_resolver import find_subgroup_cfg
from app.crm.store import (
    _table_ref,
    enrich_features_field_observed,
    fetch_snapshot_task_keys,
)
from app.layers.geojson import fetch_district_wkt, fetch_task_attributes_in_district
from app.layers.registry import get_registry

ETL_SYNC_SOURCE = "etl_sync"

AI_PHOTO_SUBGROUP = "Фото после обработки ИИ"
LENS_PHOTO_SUBGROUP = "Фото разрывий и строек"


def is_etl_sync_subgroup(subgroup_name: str, cfg: dict[str, Any] | None = None) -> bool:
    if cfg is None:
        cfg = crm_tasks_config()
    for group_cfg in cfg.get("groups", []):
        for sub_cfg in group_cfg.get("subgroups", []):
            if sub_cfg.get("name") == subgroup_name and sub_cfg.get("source") == ETL_SYNC_SOURCE:
                return True
    return False


def is_etl_sync_cfg(sub_cfg: dict[str, Any] | None) -> bool:
    return bool(sub_cfg and sub_cfg.get("source") == ETL_SYNC_SOURCE)


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


def collect_etl_sync_subgroup_tasks(
    conn: PgConnection,
    rayon: str,
    subgroup_name: str,
    apply_date_filter: bool,
) -> tuple[list[Any], list[str]]:
    """Active tasks for ETL-synced photo subgroups (JOIN crm.tasks, no persist)."""
    from app.crm.collector import TaskFeature

    del apply_date_filter  # photo subgroups have no date_field

    cfg = crm_tasks_config()
    store_cfg = crm_task_store_config()
    registry = get_registry()
    errors: list[str] = []

    if not store_cfg:
        return [], errors

    sub_cfg = find_subgroup_cfg(cfg, subgroup_name)
    if not is_etl_sync_cfg(sub_cfg):
        return [], [f"Subgroup is not etl_sync: {subgroup_name}"]

    mapping = store_cfg.get("subgroups", {}).get(subgroup_name, {})
    source_field = mapping.get("source_field")
    task_column = mapping.get("task_column")
    if not source_field or not task_column:
        return [], [f"No task store mapping for subgroup «{subgroup_name}»"]

    district_wkt, metric_srid, district_errors = _district_context(conn, rayon)
    errors.extend(district_errors)
    if not district_wkt:
        return [], errors

    layer_names = sub_cfg.get("layers", []) if sub_cfg else []
    group_names = sub_cfg.get("groups", []) if sub_cfg else []
    resolved_layers, missing = registry.resolve_subgroup_layers(layer_names, group_names)
    for name in missing:
        errors.append(f"Layer or group not found: {name}")

    tasks_schema, tasks_table = _table_ref(store_cfg)
    snapshot_keys = fetch_snapshot_task_keys(conn, store_cfg)
    features: list[Any] = []

    for layer in resolved_layers:
        try:
            raw_features = fetch_task_attributes_in_district(
                conn,
                layer,
                source_field,
                task_column,
                tasks_schema,
                tasks_table,
                district_wkt,
                metric_srid,
                scoped_geometry_id=bool(mapping.get("scoped_geometry_id")),
            )
        except Exception as exc:
            errors.append(f"{layer.display_name}: {exc}")
            continue

        for item in raw_features:
            task_key = item.get("task_key")
            if task_key and task_key in snapshot_keys:
                continue
            features.append(
                TaskFeature(
                    layer_name=item["layer_name"],
                    layer_key=item["layer_key"],
                    attributes=item["attributes"],
                    geometry=item.get("geometry"),
                    task_key=task_key,
                )
            )

    if features:
        enrich_features_field_observed(features, conn, store_cfg, subgroup_name)

    return features, errors
