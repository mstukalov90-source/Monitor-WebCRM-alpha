"""GeoJSON feature queries from PostGIS."""

from __future__ import annotations

import json
import re
from typing import Any

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

from app.layers.registry import LayerDef

_ITEMS_LINK_TABLE_RE = re.compile(
    r'^"?data_mos"?\."?items_\d+_(?:points|lines|polygons)"?$'
)


def _is_data_mos_items_table(qualified_table: str) -> bool:
    return bool(_ITEMS_LINK_TABLE_RE.match(qualified_table))


def _parse_bbox(bbox_str: str) -> tuple[float, float, float, float]:
    parts = [float(x.strip()) for x in bbox_str.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must be minLon,minLat,maxLon,maxLat")
    return parts[0], parts[1], parts[2], parts[3]


def fetch_geojson(
    conn: PgConnection,
    layer: LayerDef,
    bbox: str,
    limit: int = 2000,
) -> dict[str, Any]:
    min_lon, min_lat, max_lon, max_lat = _parse_bbox(bbox)
    geom_col = layer.geometry_column
    table = layer.qualified_table
    filters = [
        f'"{geom_col}" IS NOT NULL',
        f"""ST_Intersects(
            "{geom_col}",
            ST_Transform(
                ST_MakeEnvelope(%s, %s, %s, %s, 4326),
                ST_SRID("{geom_col}")
            )
        )""",
    ]
    params: list[Any] = [min_lon, min_lat, max_lon, max_lat]

    if layer.sql_filter:
        filters.append(f"({layer.sql_filter})")

    where = " AND ".join(filters)
    query = f"""
        SELECT json_build_object(
            'type', 'FeatureCollection',
            'features', COALESCE(json_agg(feature), '[]'::json)
        ) AS geojson
        FROM (
            SELECT json_build_object(
                'type', 'Feature',
                'id', row_number,
                'geometry', ST_AsGeoJSON(
                    ST_Transform("{geom_col}", 4326)
                )::json,
                'properties', to_jsonb(t) - '{geom_col}'
            ) AS feature
            FROM (
                SELECT *, ROW_NUMBER() OVER () AS row_number
                FROM {table}
                WHERE {where}
                LIMIT %s
            ) t
        ) sub
    """
    params.append(limit)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        row = cur.fetchone()
    if row and row["geojson"]:
        return row["geojson"]
    return {"type": "FeatureCollection", "features": []}


def _district_spatial_filter(
    layer: LayerDef,
    district_wkt: str,
    metric_srid: int,
    table_alias: str | None = None,
) -> tuple[str, list[Any]]:
    geom_col = layer.geometry_column
    geom_ref = f'{table_alias}."{geom_col}"' if table_alias else f'"{geom_col}"'
    is_point = layer.geometry_type == "point"
    district_in_layer = f"""
        ST_Transform(
            ST_GeomFromText(%s, {metric_srid}),
            ST_SRID({geom_ref})
        )
    """
    if is_point:
        spatial = f"ST_Contains({district_in_layer}, {geom_ref})"
    else:
        spatial = f"ST_Intersects({geom_ref}, {district_in_layer})"
    return spatial, [district_wkt]


def fetch_task_attributes_in_district(
    conn: PgConnection,
    layer: LayerDef,
    source_field: str,
    task_column: str,
    tasks_schema: str,
    tasks_table: str,
    district_wkt: str,
    metric_srid: int = 32637,
    *,
    scoped_geometry_id: bool = False,
) -> list[dict[str, Any]]:
    """Атрибуты объектов в районе, которые уже есть в crm.tasks."""
    from app.crm.store import scoped_business_id_expr

    geom_col = layer.geometry_column
    table = layer.qualified_table
    spatial, params = _district_spatial_filter(layer, district_wkt, metric_srid, table_alias="t")

    business_id_expr = scoped_business_id_expr(layer, source_field, scoped_geometry_id)
    filters = [
        f't."{geom_col}" IS NOT NULL',
        spatial,
        f't."{source_field}" IS NOT NULL',
        f'{business_id_expr} <> \'\'',
        f'ct."{task_column}" IS NOT NULL',
    ]
    if layer.sql_filter:
        filters.append(f"({layer.sql_filter})")

    where = " AND ".join(filters)
    query = f"""
        SELECT DISTINCT ON (ct.key)
               ct.key::text AS task_key,
               ct.field_observed,
               to_jsonb(t) - '{geom_col}' AS attrs,
               ST_AsGeoJSON(ST_Transform(t."{geom_col}", 4326))::json AS geometry
        FROM {table} t
        INNER JOIN "{tasks_schema}"."{tasks_table}" ct
            ON ct."{task_column}" = {business_id_expr}
        WHERE {where}
        ORDER BY ct.key, t."{layer.primary_key or 'id'}"
    """

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    features = []
    for row in rows:
        attrs = dict(row["attrs"]) if row["attrs"] else {}
        field_observed = row.get("field_observed")
        if field_observed is not None:
            attrs["field_observed"] = bool(field_observed)
        features.append({
            "layer_name": layer.display_name,
            "layer_key": layer.layer_key,
            "attributes": attrs,
            "geometry": row["geometry"],
            "task_key": row.get("task_key"),
        })
    return features


def fetch_attributes_in_district(
    conn: PgConnection,
    layer: LayerDef,
    district_wkt: str,
    metric_srid: int = 32637,
    *,
    source_field: str | None = None,
    include_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Атрибуты объектов в районе без геометрии."""
    if include_ids is not None and not include_ids:
        return []

    geom_col = layer.geometry_column
    table = layer.qualified_table
    spatial, params = _district_spatial_filter(layer, district_wkt, metric_srid)

    filters = [f'"{geom_col}" IS NOT NULL', spatial]
    if layer.sql_filter:
        filters.append(f"({layer.sql_filter})")
    if include_ids is not None and source_field:
        filters.append(f'"{source_field}"::text = ANY(%s)')
        params.append(include_ids)

    where = " AND ".join(filters)
    query = f"""
        SELECT to_jsonb(t) - '{geom_col}' AS attrs
        FROM {table} t
        WHERE {where}
    """

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    features = []
    for row in rows:
        attrs = dict(row["attrs"]) if row["attrs"] else {}
        features.append({
            "layer_name": layer.display_name,
            "layer_key": layer.layer_key,
            "attributes": attrs,
        })
    return features


def fetch_features_by_business_ids(
    conn: PgConnection,
    layer: LayerDef,
    source_field: str,
    business_ids: list[str],
    district_wkt: str,
    metric_srid: int = 32637,
) -> list[dict[str, Any]]:
    """Геометрии только для указанных business_id в пределах района."""
    if not business_ids:
        return []

    geom_col = layer.geometry_column
    table = layer.qualified_table
    spatial, spatial_params = _district_spatial_filter(layer, district_wkt, metric_srid)

    filters = [
        f'"{geom_col}" IS NOT NULL',
        spatial,
        f'"{source_field}"::text = ANY(%s)',
    ]
    if layer.sql_filter:
        filters.append(f"({layer.sql_filter})")

    where = " AND ".join(filters)
    query = f"""
        SELECT to_jsonb(t) - '{geom_col}' AS attrs,
               ST_AsGeoJSON(ST_Transform("{geom_col}", 4326))::json AS geometry
        FROM {table} t
        WHERE {where}
    """
    params: list[Any] = spatial_params + [business_ids]

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    features = []
    for row in rows:
        attrs = dict(row["attrs"]) if row["attrs"] else {}
        features.append({
            "layer_name": layer.display_name,
            "layer_key": layer.layer_key,
            "attributes": attrs,
            "geometry": row["geometry"],
            "business_id": str(attrs.get(source_field, "")),
        })
    return features


def fetch_features_in_district(
    conn: PgConnection,
    layer: LayerDef,
    district_wkt: str,
    metric_srid: int = 32637,
) -> list[dict[str, Any]]:
    geom_col = layer.geometry_column
    table = layer.qualified_table
    spatial, params = _district_spatial_filter(layer, district_wkt, metric_srid)

    filters = [f'"{geom_col}" IS NOT NULL', spatial]
    if layer.sql_filter:
        filters.append(f"({layer.sql_filter})")

    where = " AND ".join(filters)
    query = f"""
        SELECT to_jsonb(t) - '{geom_col}' AS attrs,
               ST_AsGeoJSON(ST_Transform("{geom_col}", 4326))::json AS geometry
        FROM {table} t
        WHERE {where}
    """

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    features = []
    for row in rows:
        attrs = dict(row["attrs"]) if row["attrs"] else {}
        features.append({
            "layer_name": layer.display_name,
            "layer_key": layer.layer_key,
            "attributes": attrs,
            "geometry": row["geometry"],
        })
    return features


def lookup_features(
    conn: PgConnection,
    layer: LayerDef,
    source_field: str,
    business_id: str,
) -> list[dict[str, Any]]:
    """All features matching business_id (points, lines, polygons rows)."""
    geom_col = layer.geometry_column
    table = layer.qualified_table
    filters = [f'"{source_field}"::text = %s', f'"{geom_col}" IS NOT NULL']
    if layer.sql_filter:
        filters.append(f"({layer.sql_filter})")
    where = " AND ".join(filters)
    query = f"""
        SELECT to_jsonb(t) - '{geom_col}' AS attrs,
               ST_AsGeoJSON(ST_Transform("{geom_col}", 4326))::json AS geometry
        FROM {table} t
        WHERE {where}
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (business_id,))
        rows = cur.fetchall()

    features: list[dict[str, Any]] = []
    for row in rows:
        geometry = row.get("geometry")
        if not geometry:
            continue
        features.append(
            {
                "layer_name": layer.display_name,
                "layer_key": layer.layer_key,
                "attributes": dict(row["attrs"]) if row["attrs"] else {},
                "geometry": geometry,
                "source_field": source_field,
                "business_id": business_id,
            }
        )
    return features


def lookup_feature(
    conn: PgConnection,
    layer: LayerDef,
    source_field: str,
    business_id: str,
) -> dict[str, Any] | None:
    features = lookup_features(conn, layer, source_field, business_id)
    return features[0] if features else None


def fetch_geometry_by_task_key(
    conn: PgConnection,
    task_key: str,
    store_cfg: dict[str, Any],
) -> dict[str, Any] | None:
    """Fetch geometry from items_* split table by crm.tasks.key."""
    from app.config import crm_tasks_config
    from app.layers.registry import get_registry

    registry = get_registry()
    crm_cfg = crm_tasks_config()

    for group_cfg in crm_cfg.get("groups", []):
        for sub_cfg in group_cfg.get("subgroups", []):
            subgroup_name = sub_cfg.get("name", "")
            mapping = store_cfg.get("subgroups", {}).get(subgroup_name)
            if not mapping or not mapping.get("scoped_geometry_id"):
                continue
            layers, _ = registry.resolve_subgroup_layers(
                sub_cfg.get("layers", []),
                sub_cfg.get("groups", []),
            )
            for layer in layers:
                if not _is_data_mos_items_table(layer.qualified_table):
                    continue
                geom_col = layer.geometry_column
                query = f"""
                    SELECT ST_AsGeoJSON(ST_Transform("{geom_col}", 4326))::json AS geometry
                    FROM {layer.qualified_table}
                    WHERE task_key = %s::uuid
                    LIMIT 1
                """
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, (task_key,))
                    row = cur.fetchone()
                if row and row.get("geometry"):
                    return row["geometry"]
    return None


def fetch_feature_by_task_key(
    conn: PgConnection,
    task_key: str,
    subgroup_name: str,
    store_cfg: dict[str, Any],
) -> dict[str, Any] | None:
    """Full feature (geometry + attributes) by task_key for a subgroup."""
    from app.layers.registry import get_registry

    mapping = store_cfg.get("subgroups", {}).get(subgroup_name)
    if not mapping:
        return None

    sub_cfg = None
    from app.config import crm_tasks_config

    for group_cfg in crm_tasks_config().get("groups", []):
        for sub in group_cfg.get("subgroups", []):
            if sub.get("name") == subgroup_name:
                sub_cfg = sub
                break

    if sub_cfg is None:
        return None

    registry = get_registry()
    layers, _ = registry.resolve_subgroup_layers(
        sub_cfg.get("layers", []),
        sub_cfg.get("groups", []),
    )
    for layer in layers:
        if not _is_data_mos_items_table(layer.qualified_table):
            continue
        geom_col = layer.geometry_column
        query = f"""
            SELECT to_jsonb(t) - '{geom_col}' AS attrs,
                   ST_AsGeoJSON(ST_Transform(t."{geom_col}", 4326))::json AS geometry
            FROM {layer.qualified_table} t
            WHERE t.task_key = %s::uuid
            LIMIT 1
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (task_key,))
            row = cur.fetchone()
        if row and row.get("geometry"):
            return {
                "layer_name": layer.display_name,
                "layer_key": layer.layer_key,
                "attributes": dict(row["attrs"]) if row["attrs"] else {},
                "geometry": row["geometry"],
            }
    return None


def normalize_rayon_name(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def fetch_district_wkt(
    conn: PgConnection,
    rayon: str,
    schema: str = "odh_export",
    table: str = "hood",
    field: str = "rayon",
    metric_srid: int = 32637,
) -> str | None:
    normalized = normalize_rayon_name(rayon)
    if not normalized:
        return None
    query = f"""
        SELECT ST_AsText(
            ST_Union(
                ST_Transform(geom, {metric_srid})
            )
        ) AS wkt
        FROM "{schema}"."{table}"
        WHERE regexp_replace(trim("{field}"::text), '\\s+', ' ', 'g') = %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (normalized,))
        row = cur.fetchone()
    if row and row[0]:
        return row[0]
    return None


def list_districts(
    conn: PgConnection,
    schema: str = "odh_export",
    table: str = "hood",
    field: str = "rayon",
    *,
    exclude_okrug_shor: list[str] | None = None,
    allowed_gids: list[int] | None = None,
) -> list[str]:
    filters = [
        f'"{field}" IS NOT NULL',
        f'TRIM("{field}"::text) <> \'\'',
    ]
    params: list = []
    if exclude_okrug_shor:
        placeholders = ", ".join(["%s"] * len(exclude_okrug_shor))
        filters.append(
            f'TRIM(COALESCE("okrug_shor", \'\')::text) NOT IN ({placeholders})'
        )
        params.extend(exclude_okrug_shor)
    if allowed_gids is not None:
        filters.append('"gid" = ANY(%s)')
        params.append(allowed_gids)
    where = " AND ".join(filters)
    query = f"""
        SELECT DISTINCT "{field}" AS rayon
        FROM "{schema}"."{table}"
        WHERE {where}
        ORDER BY 1
    """
    with conn.cursor() as cur:
        cur.execute(query, params)
        return [row[0] for row in cur.fetchall()]


def list_districts_with_gid(
    conn: PgConnection,
    schema: str = "odh_export",
    table: str = "hood",
    field: str = "rayon",
    *,
    exclude_okrug_shor: list[str] | None = None,
) -> list[dict[str, Any]]:
    filters = [
        f'"{field}" IS NOT NULL',
        f'TRIM("{field}"::text) <> \'\'',
        '"gid" IS NOT NULL',
    ]
    params: list = []
    if exclude_okrug_shor:
        placeholders = ", ".join(["%s"] * len(exclude_okrug_shor))
        filters.append(
            f'TRIM(COALESCE("okrug_shor", \'\')::text) NOT IN ({placeholders})'
        )
        params.extend(exclude_okrug_shor)
    where = " AND ".join(filters)
    query = f"""
        SELECT "gid" AS gid, "{field}" AS rayon
        FROM "{schema}"."{table}"
        WHERE {where}
        ORDER BY "{field}"
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        return [
            {"gid": int(row["gid"]), "rayon": str(row["rayon"]).strip()}
            for row in cur.fetchall()
            if row["gid"] is not None and row["rayon"]
        ]


def geometry_in_district(
    conn: PgConnection,
    geometry: dict[str, Any],
    district_wkt: str,
    metric_srid: int = 32637,
) -> bool:
    """Проверить, попадает ли GeoJSON-геометрия в полигон района."""
    import json

    geom_type = (geometry.get("type") or "").lower()
    is_point = geom_type in ("point", "multipoint")
    geom_json = json.dumps(geometry)

    district_expr = f"ST_Transform(ST_GeomFromText(%s, {metric_srid}), 4326)"
    feat_expr = "ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)"

    if is_point:
        query = f"SELECT ST_Contains({district_expr}, {feat_expr})"
        params = (district_wkt, geom_json)
    else:
        query = f"SELECT ST_Intersects({feat_expr}, {district_expr})"
        params = (geom_json, district_wkt)

    with conn.cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
    return bool(row and row[0])
