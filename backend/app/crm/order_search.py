"""City-wide search across CRM_GROUP_ORDERS source layers."""

from __future__ import annotations

import logging
from typing import Any

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

from app.config import crm_task_store_config, crm_tasks_config
from app.crm.store import CRM_GROUP_ORDERS, scoped_business_id_expr, _table_ref
from app.layers.geojson import _district_spatial_filter, fetch_district_wkt
from app.layers.registry import LayerDef, get_registry

logger = logging.getLogger(__name__)

MIN_QUERY_LENGTH = 2
MAX_HITS = 50
PER_LAYER_LIMIT = 30

SEARCH_FIELDS_BY_SUBGROUP: dict[str, tuple[str, ...]] = {
    "Ордера ОАТИ": ("order_number", "general_contractor", "customer_construction"),
    "Уведомления на земляные работы": (
        "registration_number_notifications",
        "executor",
    ),
    "Аварийно-восстановительные работы": (
        "em_call_reg_num",
        "lead_of_work",
        "balanceholder",
    ),
    "Текущие локальные ремонты": ("global_id", "customer"),
}

ID_FIELD_BY_SUBGROUP: dict[str, str] = {
    "Ордера ОАТИ": "order_number",
    "Уведомления на земляные работы": "registration_number_notifications",
    "Аварийно-восстановительные работы": "em_call_reg_num",
    "Текущие локальные ремонты": "global_id",
}

_GEOM_PRIORITY = {"polygon": 0, "line": 1, "point": 2}


def sanitize_search_query(query: str) -> str:
    """Strip LIKE wildcards; return the text used for ILIKE."""
    return "".join(ch for ch in (query or "") if ch not in "%_\\").strip()


def like_pattern(query: str) -> str:
    return f"%{sanitize_search_query(query)}%"


def _attr_text(attrs: dict[str, Any], field: str) -> str:
    value = attrs.get(field)
    if value is None:
        return ""
    return str(value).strip()


def _dedupe_key(subgroup_name: str, attrs: dict[str, Any]) -> str:
    id_field = ID_FIELD_BY_SUBGROUP.get(subgroup_name)
    if id_field:
        ident = _attr_text(attrs, id_field)
        if ident:
            return f"{subgroup_name}:{ident.casefold()}"
    source_id = _attr_text(attrs, "id")
    return f"{subgroup_name}:{source_id.casefold()}"


def _existing_columns(
    conn: PgConnection,
    schema: str,
    table: str,
    wanted: tuple[str, ...],
) -> list[str]:
    if not wanted:
        return []
    query = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s AND column_name = ANY(%s)
    """
    with conn.cursor() as cur:
        cur.execute(query, (schema, table, list(wanted)))
        found = {row[0] for row in cur.fetchall()}
    return [name for name in wanted if name in found]


def _search_layer(
    conn: PgConnection,
    layer: LayerDef,
    subgroup_name: str,
    fields: list[str],
    pattern: str,
    district_wkt: str | None,
    metric_srid: int,
    source_field: str | None,
    task_column: str | None,
    tasks_schema: str,
    tasks_table: str,
    scoped_geometry_id: bool,
) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    if not fields:
        return [], errors

    geom_col = layer.geometry_column
    table = layer.qualified_table
    like_preds = [f't."{field}"::text ILIKE %s' for field in fields]
    filters = [
        f't."{geom_col}" IS NOT NULL',
        f"({' OR '.join(like_preds)})",
    ]
    if layer.sql_filter:
        filters.append(f"({layer.sql_filter})")

    in_rayon_sql = "FALSE"
    params: list[Any] = []
    if district_wkt:
        spatial, spatial_params = _district_spatial_filter(
            layer, district_wkt, metric_srid, table_alias="t"
        )
        in_rayon_sql = spatial
        params.extend(spatial_params)
    params.extend([pattern] * len(fields))

    join_sql = ""
    select_task_key = "NULL::text AS task_key"
    if source_field and task_column:
        business_id_expr = scoped_business_id_expr(layer, source_field, scoped_geometry_id)
        join_sql = f"""
            LEFT JOIN "{tasks_schema}"."{tasks_table}" ct
                ON ct."{task_column}" = {business_id_expr}
        """
        select_task_key = "ct.key::text AS task_key"

    where = " AND ".join(filters)
    query = f"""
        SELECT
               {select_task_key},
               to_jsonb(t) - '{geom_col}' AS attrs,
               ST_AsGeoJSON(ST_Transform(t."{geom_col}", 4326))::json AS geometry,
               ({in_rayon_sql}) AS in_selected_rayon
        FROM {table} t
        {join_sql}
        WHERE {where}
        LIMIT {int(PER_LAYER_LIMIT)}
    """

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    except Exception as exc:
        conn.rollback()
        errors.append(f"{layer.display_name}: {exc}")
        logger.exception("Order search failed for layer %s", layer.layer_key)
        return [], errors

    hits: list[dict[str, Any]] = []
    for row in rows:
        attrs = dict(row["attrs"]) if row["attrs"] else {}
        hits.append(
            {
                "subgroup_name": subgroup_name,
                "layer_name": layer.display_name,
                "layer_key": layer.layer_key,
                "task_key": row.get("task_key"),
                "attributes": attrs,
                "geometry": row.get("geometry"),
                "in_selected_rayon": bool(row.get("in_selected_rayon")),
                "_geom_priority": _GEOM_PRIORITY.get(layer.geometry_type, 9),
            }
        )
    return hits, errors


def search_order_group(
    conn: PgConnection,
    query: str,
    rayon: str,
) -> dict[str, Any]:
    q = sanitize_search_query(query)
    hits: list[dict[str, Any]] = []
    errors: list[str] = []

    if len(q) < MIN_QUERY_LENGTH:
        return {
            "query": q,
            "rayon": rayon,
            "hits": [],
            "errors": [f"Введите не меньше {MIN_QUERY_LENGTH} символов"],
        }

    crm_cfg = crm_tasks_config()
    store_cfg = crm_task_store_config()
    registry = get_registry()
    pattern = like_pattern(q)

    metric_crs = crm_cfg.get("metric_crs", "EPSG:32637")
    metric_srid = int(metric_crs.split(":")[-1]) if ":" in str(metric_crs) else 32637
    district_cfg = crm_cfg.get("district_filter", {})
    district_wkt = fetch_district_wkt(
        conn,
        rayon,
        "odh_export",
        "hood",
        district_cfg.get("field", "rayon"),
        metric_srid,
    )
    if rayon and not district_wkt:
        errors.append(f"District polygon not found for «{rayon}»")

    tasks_schema, tasks_table = _table_ref(store_cfg) if store_cfg else ("crm", "tasks")
    subgroup_mappings = (store_cfg or {}).get("subgroups", {})

    group_cfg = next(
        (g for g in crm_cfg.get("groups", []) if g.get("name") == CRM_GROUP_ORDERS),
        None,
    )
    if group_cfg is None:
        return {
            "query": q,
            "rayon": rayon,
            "hits": [],
            "errors": [f"Группа «{CRM_GROUP_ORDERS}» не найдена в конфигурации"],
        }

    raw_hits: list[dict[str, Any]] = []
    for sub_cfg in group_cfg.get("subgroups", []):
        subgroup_name = sub_cfg.get("name", "")
        wanted = SEARCH_FIELDS_BY_SUBGROUP.get(subgroup_name)
        if not wanted:
            continue

        mapping = subgroup_mappings.get(subgroup_name, {})
        source_field = mapping.get("source_field")
        task_column = mapping.get("task_column")
        scoped = bool(mapping.get("scoped_geometry_id"))

        resolved, missing = registry.resolve_subgroup_layers(
            sub_cfg.get("layers", []),
            sub_cfg.get("groups", []),
        )
        for name in missing:
            errors.append(f"{subgroup_name}: слой не найден ({name})")

        for layer in resolved:
            fields = _existing_columns(conn, layer.schema, layer.table_name, wanted)
            if not fields:
                errors.append(
                    f"{layer.display_name}: нет колонок поиска ({', '.join(wanted)})"
                )
                continue
            layer_hits, layer_errors = _search_layer(
                conn,
                layer,
                subgroup_name,
                fields,
                pattern,
                district_wkt,
                metric_srid,
                source_field,
                task_column,
                tasks_schema,
                tasks_table,
                scoped,
            )
            raw_hits.extend(layer_hits)
            errors.extend(layer_errors)

    raw_hits.sort(
        key=lambda item: (
            0 if item.get("in_selected_rayon") else 1,
            item.get("subgroup_name") or "",
            _dedupe_key(item.get("subgroup_name") or "", item.get("attributes") or {}),
            item.get("_geom_priority", 9),
        )
    )

    seen: set[str] = set()
    for item in raw_hits:
        key = _dedupe_key(item.get("subgroup_name") or "", item.get("attributes") or {})
        if key in seen:
            continue
        seen.add(key)
        item.pop("_geom_priority", None)
        hits.append(item)
        if len(hits) >= MAX_HITS:
            break

    return {
        "query": q,
        "rayon": rayon,
        "hits": hits,
        "errors": errors,
    }
