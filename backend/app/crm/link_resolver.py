"""Resolve linked feature geometries from crm.tasks link columns."""

from __future__ import annotations

import json
from typing import Any

from psycopg2.extensions import connection as PgConnection

from app.config import crm_tasks_config
from app.crm.store import LINK_COLUMNS_BY_GROUP, TaskRecord, _normalize_id_value
from app.layers.geojson import lookup_features
from app.layers.registry import LayerRegistry


def subgroup_for_column(store_cfg: dict[str, Any], task_column: str) -> str | None:
    for name, mapping in store_cfg.get("subgroups", {}).items():
        if mapping.get("task_column") == task_column:
            return name
    return None


def find_subgroup_cfg(crm_cfg: dict[str, Any], subgroup_name: str) -> dict[str, Any] | None:
    for group_cfg in crm_cfg.get("groups", []):
        for sub_cfg in group_cfg.get("subgroups", []):
            if sub_cfg.get("name") == subgroup_name:
                return sub_cfg
    return None


def resolve_link_layer_infos(
    store_cfg: dict[str, Any],
    registry: LayerRegistry,
    task_columns: list[str],
) -> list[dict[str, Any]]:
    """Layer metadata for link pick on map."""
    crm_cfg = crm_tasks_config()
    layers_info: list[dict[str, Any]] = []

    for task_column in task_columns:
        subgroup_name = subgroup_for_column(store_cfg, task_column)
        if not subgroup_name:
            continue

        sub_cfg = find_subgroup_cfg(crm_cfg, subgroup_name)
        if sub_cfg is None:
            continue

        layer_defs, _ = registry.resolve_subgroup_layers(
            sub_cfg.get("layers", []),
            sub_cfg.get("groups", []),
        )
        mapping = store_cfg["subgroups"][subgroup_name]
        for layer in layer_defs:
            layers_info.append(
                {
                    "task_column": task_column,
                    "subgroup_name": subgroup_name,
                    "layer_key": layer.layer_key,
                    "display_name": layer.display_name,
                    "source_field": mapping.get("source_field"),
                }
            )

    return layers_info


def resolve_linked_features(
    conn: PgConnection,
    record: TaskRecord,
    group_name: str,
    store_cfg: dict[str, Any],
    registry: LayerRegistry,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Return linked features and link columns that could not be resolved."""
    link_columns = LINK_COLUMNS_BY_GROUP.get(group_name, ())
    crm_cfg = crm_tasks_config()
    results: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    seen_geometries: set[str] = set()

    for link_column in link_columns:
        value = _normalize_id_value(getattr(record, link_column))
        if value is None:
            continue

        subgroup_name = subgroup_for_column(store_cfg, link_column)
        if not subgroup_name:
            missing.append({"link_column": link_column, "business_id": value})
            continue

        sub_cfg = find_subgroup_cfg(crm_cfg, subgroup_name)
        if sub_cfg is None:
            missing.append({"link_column": link_column, "business_id": value})
            continue

        mapping = store_cfg["subgroups"][subgroup_name]
        source_field = mapping.get("source_field")
        if not source_field:
            missing.append({"link_column": link_column, "business_id": value})
            continue

        layer_defs, _ = registry.resolve_subgroup_layers(
            sub_cfg.get("layers", []),
            sub_cfg.get("groups", []),
        )

        found = False
        for layer in layer_defs:
            for feat in lookup_features(conn, layer, source_field, value):
                dedupe_key = f"{feat['layer_key']}:{value}:{json.dumps(feat.get('geometry'), sort_keys=True)}"
                if dedupe_key in seen_keys:
                    found = True
                    continue

                geometry = feat.get("geometry")
                if geometry:
                    geom_key = json.dumps(geometry, sort_keys=True)
                    if geom_key in seen_geometries:
                        found = True
                        continue
                    seen_geometries.add(geom_key)

                seen_keys.add(dedupe_key)
                results.append(
                    {
                        "link_column": link_column,
                        "layer_key": feat["layer_key"],
                        "layer_name": feat["layer_name"],
                        "geometry": geometry,
                        "attributes": feat.get("attributes", {}),
                        "business_id": value,
                    }
                )
                found = True

        if not found:
            missing.append({"link_column": link_column, "business_id": value})

    return results, missing
