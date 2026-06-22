"""CRM task collection via PostGIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from psycopg2.extensions import connection as PgConnection

from app.config import crm_task_store_config, crm_tasks_config
from app.crm.date_utils import attribute_matches_date_range
from app.crm.link_resolver import find_subgroup_cfg
from app.crm.store import (
    PersistStats,
    _table_ref,
    enrich_features_field_observed,
    enrich_task_result_field_observed,
    fetch_snapshot_task_keys,
    filter_sent_tasks_from_result,
    persist_new_tasks_in_district,
)
from app.layers.geojson import fetch_district_wkt, fetch_task_attributes_in_district
from app.layers.registry import get_registry


@dataclass
class CollectLayerPlanItem:
    group_name: str
    subgroup_name: str
    layer_key: str
    layer_name: str


@dataclass
class TaskFeature:
    layer_name: str
    layer_key: str
    attributes: dict[str, Any]
    geometry: dict[str, Any] | None = None
    task_key: str | None = None
    sent_at: str | None = None


@dataclass
class TaskSubgroup:
    name: str
    features: list[TaskFeature] = field(default_factory=list)
    date_field: str | None = None


@dataclass
class TaskGroup:
    name: str
    subgroups: list[TaskSubgroup] = field(default_factory=list)


@dataclass
class TaskResult:
    district_name: str
    filter_date_from: date
    filter_date_to: date
    apply_date_filter: bool = True
    groups: list[TaskGroup] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def total_count(self) -> int:
        return sum(len(s.features) for g in self.groups for s in g.subgroups)


def _date_filter_range(lookback_days: int) -> tuple[date, date]:
    today = date.today()
    return today - timedelta(days=lookback_days), today


def persist_district_tasks(
    conn: PgConnection,
    rayon: str,
    apply_date_filter: bool,
) -> PersistStats:
    """Добавить новые задачи района в crm.tasks (INSERT ... SELECT на стороне БД)."""
    cfg = crm_tasks_config()
    store_cfg = crm_task_store_config()
    registry = get_registry()
    lookback_days = int(cfg.get("date_lookback_days", 3))
    date_from, date_to = _date_filter_range(lookback_days)
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
    if not district_wkt:
        return PersistStats()

    stats = PersistStats()
    if not store_cfg:
        return stats

    for group_cfg in cfg.get("groups", []):
        group_name = group_cfg.get("name", "")
        for sub_cfg in group_cfg.get("subgroups", []):
            subgroup_name = sub_cfg.get("name", "")
            layers, _missing = registry.resolve_subgroup_layers(
                sub_cfg.get("layers", []),
                sub_cfg.get("groups", []),
            )
            date_field = sub_cfg.get("date_field") if apply_date_filter else None
            for layer in layers:
                try:
                    stats.inserted += persist_new_tasks_in_district(
                        conn,
                        group_name,
                        subgroup_name,
                        layer,
                        store_cfg,
                        district_wkt,
                        metric_srid,
                        date_field,
                        date_from if date_field else None,
                        date_to if date_field else None,
                    )
                except Exception:
                    stats.invalid += 1
    return stats


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


def build_collect_plan(
    rayon: str,
    apply_date_filter: bool,
) -> tuple[TaskResult, list[CollectLayerPlanItem]]:
    cfg = crm_tasks_config()
    registry = get_registry()
    lookback_days = int(cfg.get("date_lookback_days", 3))
    date_from, date_to = _date_filter_range(lookback_days)

    result = TaskResult(
        district_name=rayon,
        filter_date_from=date_from,
        filter_date_to=date_to,
        apply_date_filter=apply_date_filter,
    )
    layers: list[CollectLayerPlanItem] = []

    for group_cfg in cfg.get("groups", []):
        group_name = group_cfg.get("name", "")
        group = TaskGroup(name=group_name)
        for sub_cfg in group_cfg.get("subgroups", []):
            subgroup_name = sub_cfg.get("name", "")
            layer_names = sub_cfg.get("layers", [])
            group_names = sub_cfg.get("groups", [])
            resolved_layers, missing = registry.resolve_subgroup_layers(layer_names, group_names)
            for name in missing:
                result.errors.append(f"Layer or group not found: {name}")

            date_field = sub_cfg.get("date_field") if apply_date_filter else None
            group.subgroups.append(
                TaskSubgroup(name=subgroup_name, date_field=date_field)
            )
            for layer in resolved_layers:
                layers.append(
                    CollectLayerPlanItem(
                        group_name=group_name,
                        subgroup_name=subgroup_name,
                        layer_key=layer.layer_key,
                        layer_name=layer.display_name,
                    )
                )
        result.groups.append(group)

    return result, layers


def collect_layer_tasks(
    conn: PgConnection,
    rayon: str,
    apply_date_filter: bool,
    group_name: str,
    subgroup_name: str,
    layer_key: str,
) -> tuple[list[TaskFeature], list[str]]:
    cfg = crm_tasks_config()
    store_cfg = crm_task_store_config()
    registry = get_registry()
    errors: list[str] = []

    if not store_cfg:
        return [], errors

    sub_cfg = find_subgroup_cfg(cfg, subgroup_name)
    if sub_cfg is None:
        return [], [f"Subgroup not found: {subgroup_name}"]

    layer = registry.by_key.get(layer_key)
    if layer is None:
        return [], [f"Layer not found: {layer_key}"]

    mapping = store_cfg.get("subgroups", {}).get(subgroup_name, {})
    source_field = mapping.get("source_field")
    task_column = mapping.get("task_column")
    if not source_field or not task_column:
        return [], [f"No task store mapping for subgroup «{subgroup_name}»"]

    district_wkt, metric_srid, district_errors = _district_context(conn, rayon)
    errors.extend(district_errors)
    if not district_wkt:
        return [], errors

    lookback_days = int(cfg.get("date_lookback_days", 3))
    date_from, date_to = _date_filter_range(lookback_days)
    date_field = sub_cfg.get("date_field") if apply_date_filter else None

    tasks_schema, tasks_table = _table_ref(store_cfg)
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
        )
    except Exception as exc:
        return [], [f"{layer.display_name}: {exc}"]

    snapshot_keys = fetch_snapshot_task_keys(conn, store_cfg)
    features: list[TaskFeature] = []
    for item in raw_features:
        if date_field and not attribute_matches_date_range(
            item["attributes"],
            date_field,
            date_from,
            date_to,
        ):
            continue
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


def collect_tasks(
    conn: PgConnection,
    rayon: str,
    apply_date_filter: bool,
    *,
    persist: bool = True,
    filter_sent: bool = True,
) -> tuple[TaskResult, Any]:
    result, layers = build_collect_plan(rayon, apply_date_filter)
    if result.errors and not layers:
        return result, None

    subgroup_index: dict[tuple[str, str], TaskSubgroup] = {}
    for group in result.groups:
        for subgroup in group.subgroups:
            subgroup_index[(group.name, subgroup.name)] = subgroup

    for chunk in layers:
        features, layer_errors = collect_layer_tasks(
            conn,
            rayon,
            apply_date_filter,
            chunk.group_name,
            chunk.subgroup_name,
            chunk.layer_key,
        )
        result.errors.extend(layer_errors)
        subgroup = subgroup_index.get((chunk.group_name, chunk.subgroup_name))
        if subgroup is not None:
            subgroup.features.extend(features)

    if filter_sent:
        store_cfg = crm_task_store_config()
        if store_cfg:
            filter_sent_tasks_from_result(result, conn, store_cfg)

    store_cfg = crm_task_store_config()
    if store_cfg:
        enrich_task_result_field_observed(result, conn, store_cfg)

    return result, None


def collect_plan_to_dict(result: TaskResult, layers: list[CollectLayerPlanItem]) -> dict[str, Any]:
    data = task_result_to_dict(result)
    data["layers"] = [
        {
            "group_name": item.group_name,
            "subgroup_name": item.subgroup_name,
            "layer_key": item.layer_key,
            "layer_name": item.layer_name,
        }
        for item in layers
    ]
    return data


def collect_layer_to_dict(
    group_name: str,
    subgroup_name: str,
    layer_key: str,
    features: list[TaskFeature],
    errors: list[str],
) -> dict[str, Any]:
    return {
        "group_name": group_name,
        "subgroup_name": subgroup_name,
        "layer_key": layer_key,
        "features": [
            {
                "layer_name": f.layer_name,
                "layer_key": f.layer_key,
                "attributes": f.attributes,
                "geometry": f.geometry,
                "task_key": f.task_key,
                "sent_at": f.sent_at,
            }
            for f in features
        ],
        "errors": errors,
    }


def task_result_to_dict(result: TaskResult, persist_stats=None) -> dict[str, Any]:
    data = {
        "district_name": result.district_name,
        "filter_date_from": result.filter_date_from.isoformat(),
        "filter_date_to": result.filter_date_to.isoformat(),
        "apply_date_filter": result.apply_date_filter,
        "errors": result.errors,
        "groups": [
            {
                "name": g.name,
                "subgroups": [
                    {
                        "name": s.name,
                        "date_field": s.date_field,
                        "features": [
                            {
                                "layer_name": f.layer_name,
                                "layer_key": f.layer_key,
                                "attributes": f.attributes,
                                "geometry": f.geometry,
                                "task_key": f.task_key,
                                "sent_at": f.sent_at,
                            }
                            for f in s.features
                        ],
                    }
                    for s in g.subgroups
                ],
            }
            for g in result.groups
        ],
    }
    if persist_stats is not None:
        data["persist_stats"] = {
            "inserted": persist_stats.inserted,
            "skipped": persist_stats.skipped,
            "invalid": persist_stats.invalid,
        }
    return data
