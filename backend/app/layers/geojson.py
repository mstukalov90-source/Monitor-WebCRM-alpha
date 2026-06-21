"""GeoJSON feature queries from PostGIS."""

from __future__ import annotations

import json
from typing import Any

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

from app.layers.registry import LayerDef


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
) -> list[dict[str, Any]]:
    """Атрибуты объектов в районе, которые уже есть в crm.tasks."""
    geom_col = layer.geometry_column
    table = layer.qualified_table
    spatial, params = _district_spatial_filter(layer, district_wkt, metric_srid, table_alias="t")

    filters = [
        f't."{geom_col}" IS NOT NULL',
        spatial,
        f't."{source_field}" IS NOT NULL',
        f'ct."{task_column}" IS NOT NULL',
    ]
    if layer.sql_filter:
        filters.append(f"({layer.sql_filter})")

    where = " AND ".join(filters)
    query = f"""
        SELECT ct.key::text AS task_key,
               to_jsonb(t) - '{geom_col}' AS attrs,
               ST_AsGeoJSON(ST_Transform(t."{geom_col}", 4326))::json AS geometry
        FROM {table} t
        INNER JOIN "{tasks_schema}"."{tasks_table}" ct
            ON ct."{task_column}" = t."{source_field}"::text
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


def fetch_district_wkt(
    conn: PgConnection,
    rayon: str,
    schema: str = "odh_export",
    table: str = "hood",
    field: str = "rayon",
    metric_srid: int = 32637,
) -> str | None:
    query = f"""
        SELECT ST_AsText(
            ST_Union(
                ST_Transform(geom, {metric_srid})
            )
        ) AS wkt
        FROM "{schema}"."{table}"
        WHERE "{field}" = %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (rayon,))
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
) -> list[str]:
    filters = [
        f'"{field}" IS NOT NULL',
        f'TRIM("{field}"::text) <> \'\'',
    ]
    if exclude_okrug_shor:
        placeholders = ", ".join(["%s"] * len(exclude_okrug_shor))
        filters.append(
            f'TRIM(COALESCE("okrug_shor", \'\')::text) NOT IN ({placeholders})'
        )
    where = " AND ".join(filters)
    query = f"""
        SELECT DISTINCT "{field}" AS rayon
        FROM "{schema}"."{table}"
        WHERE {where}
        ORDER BY 1
    """
    with conn.cursor() as cur:
        if exclude_okrug_shor:
            cur.execute(query, exclude_okrug_shor)
        else:
            cur.execute(query)
        return [row[0] for row in cur.fetchall()]


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
