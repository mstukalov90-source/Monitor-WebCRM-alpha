"""Nearby map context: orders / KGS / SPS / OPS within a radius of a task."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

from app.config import crm_task_store_config, crm_tasks_config
from app.crm.snapshot_loader import _lookup_feature_for_record
from app.crm.store import _find_subgroup_for_record, fetch_task_by_key
from app.db import MggtUnavailable, get_mggt_connection
from app.layers.qgis_styles import DEFAULT_STYLE, ParsedLayerStyle, load_sps_styles
from app.layers.registry import LayerDef, get_registry

NearbyKind = Literal["orders", "kgs", "sps", "ops"]

NEARBY_RADIUS_M = 250.0
PER_TABLE_LIMIT = 500
TOTAL_CAP = 2000
METRIC_SRID_DEFAULT = 32637
MSK77_SRID = 980077
WGS84_PROJ4 = "+proj=longlat +datum=WGS84 +no_defs"
KGS_COLOR = "#800020"
ORDER_PREFIXES = ("items_2855", "items_62441", "items_62461", "items_62501")
ORDER_SUFFIXES = ("_points", "_lines", "_polygons")
SPS_SCHEMA = "sps"
KGS_SCHEMA = "kgs"
KGS_TABLE_KINDS = {
    "lines": "line",
    "point": "point",
    "points": "point",
    "kgs_line": "line",
    "kgs_lines": "line",
    "kgs_point": "point",
    "kgs_points": "point",
}

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def quote_ident(name: str) -> str:
    if not _IDENT_RE.match(name):
        raise ValueError(f"invalid identifier: {name}")
    return f'"{name}"'


def metric_srid() -> int:
    crs = crm_tasks_config().get("metric_crs", f"EPSG:{METRIC_SRID_DEFAULT}")
    if isinstance(crs, str) and ":" in crs:
        try:
            return int(crs.split(":")[-1])
        except ValueError:
            return METRIC_SRID_DEFAULT
    return METRIC_SRID_DEFAULT


def load_msk77_proj4(conn: PgConnection) -> str:
    """Proj4 of MSK-77 from monitor ``public.spatial_ref_sys`` (srid=980077)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT proj4text FROM public.spatial_ref_sys WHERE srid = %s LIMIT 1",
            (MSK77_SRID,),
        )
        row = cur.fetchone()
    text = str(row[0]).strip() if row and row[0] else ""
    if not text:
        raise RuntimeError(f"В public.spatial_ref_sys нет srid={MSK77_SRID} (МСК 77)")
    return text


def style_from_symbology(symbology: dict[str, Any] | None, geometry_type: str) -> dict[str, Any]:
    data = symbology or {}
    if geometry_type == "line":
        color = data.get("color") or "#3388ff"
        return {
            "color": color,
            "weight": max(float(data.get("width") or 2), 2),
            "opacity": float(data.get("opacity") or 0.9),
            "fillColor": color,
            "fillOpacity": 0,
            "radius": 5,
        }
    if geometry_type == "polygon":
        fill = data.get("fill_color") or data.get("outline_color") or "#3388ff"
        outline = data.get("outline_color") or fill
        return {
            "color": outline,
            "weight": float(data.get("outline_width") or 1),
            "fillColor": fill,
            "fillOpacity": float(data.get("fill_opacity") if data.get("fill_opacity") is not None else 0.5),
            "opacity": float(data.get("opacity") or 0.9),
            "radius": 5,
        }
    color = data.get("color") or data.get("center_color") or "#3388ff"
    return {
        "color": data.get("outer_color") or color,
        "weight": float(data.get("outer_width") or 1),
        "fillColor": color,
        "fillOpacity": float(data.get("opacity") or 0.9),
        "opacity": float(data.get("opacity") or 0.9),
        "radius": float(data.get("size") or 4),
    }


def kgs_style(geometry_type: str) -> dict[str, Any]:
    if geometry_type == "point":
        return {
            "color": KGS_COLOR,
            "weight": 1,
            "fillColor": KGS_COLOR,
            "fillOpacity": 0.9,
            "opacity": 0.95,
            "radius": 6,
        }
    return {
        "color": KGS_COLOR,
        "weight": 3,
        "fillColor": KGS_COLOR,
        "fillOpacity": 0.2,
        "opacity": 0.95,
        "radius": 5,
    }


def iter_order_layers(registry: Any | None = None) -> list[LayerDef]:
    source = registry or get_registry()
    layers: list[LayerDef] = []
    seen: set[str] = set()
    for layer in source.by_key.values():
        if layer.schema != "data_mos":
            continue
        table = layer.table_name
        if not any(table.startswith(prefix) for prefix in ORDER_PREFIXES):
            continue
        if not any(table.endswith(suffix) for suffix in ORDER_SUFFIXES):
            continue
        if layer.layer_key in seen:
            continue
        seen.add(layer.layer_key)
        layers.append(layer)
    layers.sort(key=lambda item: (item.table_name, item.layer_key))
    return layers


def ops_extra_where(has_state_id: bool) -> str | None:
    if not has_state_id:
        return None
    return 't."state_id" = 4'


def geometry_kind_from_type(geom_type: str | None) -> str:
    text = (geom_type or "").upper()
    if "POINT" in text:
        return "point"
    if "LINE" in text:
        return "line"
    if "POLYGON" in text or "FACE" in text:
        return "polygon"
    return "line"


def _set_local_timeout(conn: PgConnection, ms: int = 60000) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute(f"SET LOCAL statement_timeout = {int(ms)}")
    except Exception:
        conn.rollback()


def schema_exists(conn: PgConnection, schema: str) -> bool:
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s LIMIT 1",
                (schema,),
            )
            return cur.fetchone() is not None
    except Exception:
        conn.rollback()
        return False


def table_has_column(conn: PgConnection, schema: str, table: str, column: str) -> bool:
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s AND column_name = %s
                LIMIT 1
                """,
                (schema, table, column),
            )
            return cur.fetchone() is not None
    except Exception:
        conn.rollback()
        return False


def list_geometry_tables(conn: PgConnection, schema: str) -> list[tuple[str, str, str]]:
    """Return (table_name, geometry_column, geometry_kind)."""
    rows: list[tuple[str, str, str]] = []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT f_table_name, f_geometry_column, type
                FROM public.geometry_columns
                WHERE f_table_schema = %s
                ORDER BY f_table_name
                """,
                (schema,),
            )
            for row in cur.fetchall():
                table = str(row.get("f_table_name") or "")
                geom_col = str(row.get("f_geometry_column") or "")
                if not _IDENT_RE.match(table) or not _IDENT_RE.match(geom_col):
                    continue
                rows.append((table, geom_col, geometry_kind_from_type(str(row.get("type") or ""))))
    except Exception:
        conn.rollback()
    if rows:
        return rows
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT c.relname AS table_name, a.attname AS geom_col,
                       COALESCE(postgis_typmod_type(a.atttypmod), t.typname) AS geom_type
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_attribute a ON a.attrelid = c.oid
                JOIN pg_type t ON t.oid = a.atttypid
                WHERE n.nspname = %s
                  AND c.relkind = 'r'
                  AND a.attnum > 0
                  AND NOT a.attisdropped
                  AND t.typname IN ('geometry', 'geography')
                ORDER BY c.relname
                """,
                (schema,),
            )
            for row in cur.fetchall():
                table = str(row.get("table_name") or "")
                geom_col = str(row.get("geom_col") or "")
                if not _IDENT_RE.match(table) or not _IDENT_RE.match(geom_col):
                    continue
                rows.append((table, geom_col, geometry_kind_from_type(str(row.get("geom_type") or ""))))
    except Exception:
        conn.rollback()
    return rows


def features_within_radius_sql(
    schema: str,
    table: str,
    geom_col: str,
    *,
    extra_where: str | None = None,
    metric: int = METRIC_SRID_DEFAULT,
    source_proj: str | None = None,
) -> str:
    """SQL for nearby features. ``source_proj`` treats layer coords as that CRS (MSK-77)."""
    quoted_schema = quote_ident(schema)
    quoted_table = quote_ident(table)
    quoted_geom = quote_ident(geom_col)
    extra = f" AND ({extra_where})" if extra_where else ""
    if source_proj:
        return f"""
        WITH p AS (
          SELECT
            ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326) AS center_4326,
            %s::text AS wgs84,
            %s::text AS msk77
        )
        SELECT to_jsonb(t) - '{geom_col}' AS attrs,
               ST_AsGeoJSON(
                 ST_Transform(ST_SetSRID(ST_Force2D(t.{quoted_geom}), 0), p.msk77, 4326)
               )::json AS geometry
        FROM {quoted_schema}.{quoted_table} t, p
        WHERE t.{quoted_geom} IS NOT NULL
          AND ST_DWithin(
                ST_Transform(p.center_4326, p.wgs84, p.msk77),
                ST_SetSRID(ST_Force2D(t.{quoted_geom}), 0),
                %s
              ){extra}
        LIMIT %s
        """
    return f"""
        SELECT to_jsonb(t) - '{geom_col}' AS attrs,
               ST_AsGeoJSON(ST_Transform(t.{quoted_geom}, 4326))::json AS geometry
        FROM {quoted_schema}.{quoted_table} t
        WHERE t.{quoted_geom} IS NOT NULL
          AND ST_DWithin(
                ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), {int(metric)}),
                ST_Transform(t.{quoted_geom}, {int(metric)}),
                %s
              ){extra}
        LIMIT %s
    """


def features_within_radius(
    conn: PgConnection,
    schema: str,
    table: str,
    geom_col: str,
    center_geometry: dict[str, Any],
    radius_m: float,
    *,
    extra_where: str | None = None,
    metric: int = METRIC_SRID_DEFAULT,
    source_proj: str | None = None,
    limit: int = PER_TABLE_LIMIT,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Return list of (attrs, geometry) within radius of center GeoJSON geometry."""
    query = features_within_radius_sql(
        schema,
        table,
        geom_col,
        extra_where=extra_where,
        metric=metric,
        source_proj=source_proj,
    )
    center_json = json.dumps(center_geometry)
    if source_proj:
        params: tuple[Any, ...] = (
            center_json,
            WGS84_PROJ4,
            source_proj,
            radius_m,
            limit,
        )
    else:
        params = (center_json, radius_m, limit)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    except Exception:
        conn.rollback()
        raise
    results: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for row in rows:
        geometry = row.get("geometry")
        if not geometry:
            continue
        attrs = dict(row["attrs"]) if row.get("attrs") else {}
        results.append((attrs, geometry))
    return results


def _feature_id(table: str, attrs: dict[str, Any], index: int) -> str:
    for key in ("id", "gid", "ogc_fid", "fid"):
        value = attrs.get(key)
        if value is not None and str(value).strip():
            return f"{table}:{value}"
    return f"{table}:{index}"


def _pack_feature(
    *,
    table: str,
    geometry: dict[str, Any],
    attrs: dict[str, Any],
    style: dict[str, Any],
    index: int,
    label: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": _feature_id(table, attrs, index),
        "table": table,
        "geometry": geometry,
        "properties": attrs,
        "style": style,
    }
    if label:
        payload["label"] = label
    return payload


def resolve_task_geometry(
    conn: PgConnection,
    store_cfg: dict[str, Any],
    key: str,
) -> tuple[dict[str, Any] | None, str | None]:
    record = fetch_task_by_key(conn, store_cfg, key)
    if record is None:
        return None, "not_found"
    resolved = _find_subgroup_for_record(record, store_cfg)
    subgroup_name = resolved[0] if resolved else (record.type or "")
    feature = _lookup_feature_for_record(conn, record, subgroup_name, store_cfg)
    geometry = feature.get("geometry") if feature else None
    if not isinstance(geometry, dict):
        return None, "no_geometry"
    return geometry, None


def _collect_from_layers(
    conn: PgConnection,
    layers: list[LayerDef],
    center: dict[str, Any],
    radius_m: float,
    metric: int,
    errors: list[str],
) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    remaining = TOTAL_CAP
    for layer in layers:
        if remaining <= 0:
            break
        limit = min(PER_TABLE_LIMIT, remaining)
        try:
            rows = features_within_radius(
                conn,
                layer.schema,
                layer.table_name,
                layer.geometry_column,
                center,
                radius_m,
                metric=metric,
                source_proj=None,
                limit=limit,
            )
        except Exception as exc:
            errors.append(f"{layer.schema}.{layer.table_name}: {exc}")
            continue
        style = style_from_symbology(layer.symbology, layer.geometry_type)
        table = f"{layer.schema}.{layer.table_name}"
        for index, (attrs, geometry) in enumerate(rows):
            features.append(
                _pack_feature(
                    table=table,
                    geometry=geometry,
                    attrs=attrs,
                    style=style,
                    index=index,
                )
            )
        remaining = TOTAL_CAP - len(features)
    return features


def _collect_kgs(
    conn: PgConnection,
    center: dict[str, Any],
    radius_m: float,
    errors: list[str],
    *,
    source_proj: str,
) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    tables = list_geometry_tables(conn, KGS_SCHEMA)
    if not tables:
        tables = [("lines", "geom", "line"), ("point", "geom", "point")]
    remaining = TOTAL_CAP
    for table, geom_col, kind in tables:
        if table not in KGS_TABLE_KINDS:
            continue
        geometry_type = KGS_TABLE_KINDS[table]
        if remaining <= 0:
            break
        try:
            rows = features_within_radius(
                conn,
                KGS_SCHEMA,
                table,
                geom_col,
                center,
                radius_m,
                source_proj=source_proj,
                limit=min(PER_TABLE_LIMIT, remaining),
            )
        except Exception as exc:
            errors.append(f"{KGS_SCHEMA}.{table}: {exc}")
            continue
        style = kgs_style(geometry_type or kind)
        qualified = f"{KGS_SCHEMA}.{table}"
        for index, (attrs, geometry) in enumerate(rows):
            label = None
            if geometry_type == "point":
                text = attrs.get("text")
                if text is not None and str(text).strip():
                    label = str(text).strip()
            features.append(
                _pack_feature(
                    table=qualified,
                    geometry=geometry,
                    attrs=attrs,
                    style=style,
                    index=index,
                    label=label,
                )
            )
        remaining = TOTAL_CAP - len(features)
    return features


def _collect_sps(
    conn: PgConnection,
    center: dict[str, Any],
    radius_m: float,
    errors: list[str],
    *,
    source_proj: str,
    ops_only: bool,
) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    tables = list_geometry_tables(conn, SPS_SCHEMA)
    if not tables:
        errors.append("В схеме sps нет таблиц с геометрией")
        return features
    styles = load_sps_styles(conn, SPS_SCHEMA)
    remaining = TOTAL_CAP
    for table, geom_col, kind in tables:
        if remaining <= 0:
            break
        extra = None
        if ops_only:
            if not table_has_column(conn, SPS_SCHEMA, table, "state_id"):
                continue
            extra = ops_extra_where(True)
        try:
            rows = features_within_radius(
                conn,
                SPS_SCHEMA,
                table,
                geom_col,
                center,
                radius_m,
                extra_where=extra,
                source_proj=source_proj,
                limit=min(PER_TABLE_LIMIT, remaining),
            )
        except Exception as exc:
            errors.append(f"{SPS_SCHEMA}.{table}: {exc}")
            continue
        parsed: ParsedLayerStyle = styles.get(table) or ParsedLayerStyle()
        qualified = f"{SPS_SCHEMA}.{table}"
        for index, (attrs, geometry) in enumerate(rows):
            style = parsed.resolve(attrs) if parsed else dict(DEFAULT_STYLE)
            features.append(
                _pack_feature(
                    table=qualified,
                    geometry=geometry,
                    attrs=attrs,
                    style=style,
                    index=index,
                )
            )
        remaining = TOTAL_CAP - len(features)
    return features


def _kgs_from_conn(
    conn: PgConnection,
    center: dict[str, Any],
    errors: list[str],
    *,
    source_proj: str,
) -> list[dict[str, Any]]:
    if not schema_exists(conn, KGS_SCHEMA):
        return []
    _set_local_timeout(conn)
    return _collect_kgs(conn, center, NEARBY_RADIUS_M, errors, source_proj=source_proj)


def fetch_nearby_context(
    conn: PgConnection,
    key: str,
    kind: NearbyKind,
    store_cfg: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    cfg = store_cfg or crm_task_store_config()
    center, status = resolve_task_geometry(conn, cfg, key)
    if status == "not_found":
        return None
    metric = metric_srid()
    errors: list[str] = []
    if status == "no_geometry" or center is None:
        return {
            "kind": kind,
            "radius_m": NEARBY_RADIUS_M,
            "features": [],
            "errors": ["Нет геометрии у задачи"],
            "count": 0,
        }

    _set_local_timeout(conn)
    features: list[dict[str, Any]] = []
    msk77_proj: str | None = None
    if kind in ("kgs", "sps", "ops"):
        try:
            msk77_proj = load_msk77_proj4(conn)
        except Exception as exc:
            errors.append(f"Не удалось загрузить МСК 77 (srid={MSK77_SRID}): {exc}")
            return {
                "kind": kind,
                "radius_m": NEARBY_RADIUS_M,
                "features": [],
                "errors": errors,
                "count": 0,
            }
    if kind == "orders":
        features = _collect_from_layers(conn, iter_order_layers(), center, NEARBY_RADIUS_M, metric, errors)
    elif kind == "kgs":
        assert msk77_proj is not None
        if schema_exists(conn, KGS_SCHEMA):
            features = _kgs_from_conn(conn, center, errors, source_proj=msk77_proj)
        else:
            try:
                with get_mggt_connection() as mggt_conn:
                    if schema_exists(mggt_conn, KGS_SCHEMA):
                        features = _kgs_from_conn(mggt_conn, center, errors, source_proj=msk77_proj)
                    else:
                        errors.append("Схема kgs не найдена")
            except MggtUnavailable as exc:
                errors.append(f"Схема kgs не найдена в основной БД и MGGT недоступен: {exc}")
            except Exception as exc:
                errors.append(f"Не удалось прочитать КГС: {exc}")
    elif kind in ("sps", "ops"):
        assert msk77_proj is not None
        try:
            with get_mggt_connection() as mggt_conn:
                _set_local_timeout(mggt_conn)
                features = _collect_sps(
                    mggt_conn,
                    center,
                    NEARBY_RADIUS_M,
                    errors,
                    source_proj=msk77_proj,
                    ops_only=(kind == "ops"),
                )
        except MggtUnavailable as exc:
            errors.append(f"БД MGGT недоступна: {exc}")
        except Exception as exc:
            errors.append(f"Ошибка чтения схемы sps: {exc}")
    else:
        errors.append(f"Неизвестный слой: {kind}")

    return {
        "kind": kind,
        "radius_m": NEARBY_RADIUS_M,
        "features": features,
        "errors": errors,
        "count": len(features),
    }
