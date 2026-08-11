"""Field quality scoring for surveyed area orders."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor, Json

from app.config import crm_task_store_config, crm_tasks_config, order_tracks_config
from app.crm.field_data_loader import (
    _field_data_mapping,
    _reports_qualified_table,
    report_row_to_attributes,
)
from app.crm.store import FIELD_DATA_SUBGROUP
from app.crm.tracks_loader import track_row_to_attributes
from app.layers.geojson import normalize_rayon_name

FIELD_SCORE_SCHEMA = "crm"
FIELD_SCORE_TABLE = "field_score"

SCORE_VALUES = frozenset({"unsatisfactory", "satisfactory", "good"})

TRACK_BUFFER_METERS = 50.0


class FieldScoreError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def coverage_hint_from_pct(pct: float | None) -> str | None:
    if pct is None:
        return None
    if pct < 50:
        return "unsatisfactory"
    if pct < 80:
        return "satisfactory"
    return "good"


def _metric_srid() -> int:
    cfg = crm_tasks_config()
    metric_crs = cfg.get("metric_crs", "EPSG:32637")
    return int(metric_crs.split(":")[-1]) if ":" in metric_crs else 32637


def _serialize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _fetch_order(conn: PgConnection, order_key: str) -> dict[str, Any] | None:
    metric_srid = _metric_srid()
    query = f"""
        SELECT
            key::text AS order_key,
            task_number,
            rayon,
            area,
            status,
            date_survey,
            ST_AsGeoJSON(geom)::json AS geometry,
            ST_AsText(ST_Transform(geom, {metric_srid})) AS order_wkt,
            ST_Area(ST_Transform(geom, {metric_srid})) AS order_area_m2
        FROM crm.tasks_area
        WHERE key = %s::uuid
          AND geom IS NOT NULL
        LIMIT 1
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (order_key,))
        row = cur.fetchone()
    if not row:
        return None
    data = dict(row)
    geometry = data.get("geometry")
    if isinstance(geometry, str):
        geometry = json.loads(geometry)
    data["geometry"] = geometry
    data["task_number"] = (
        str(data["task_number"]).strip() if data.get("task_number") is not None else None
    )
    data["rayon"] = (
        normalize_rayon_name(str(data["rayon"])) if data.get("rayon") else None
    )
    data["area"] = float(data["area"]) if data.get("area") is not None else None
    data["date_survey"] = _serialize_value(data.get("date_survey"))
    data["order_area_m2"] = (
        float(data["order_area_m2"]) if data.get("order_area_m2") is not None else None
    )
    return data


def _fetch_closed_tasks(
    conn: PgConnection,
    *,
    order_wkt: str,
    rayon: str | None,
) -> list[dict[str, Any]]:
    """Field findings inside the order polygon (reports with photos), for scoring."""
    del rayon  # reports filtered spatially by order polygon
    store_cfg = crm_task_store_config()
    mapping = _field_data_mapping(store_cfg)
    if mapping.get("source") != "field_data":
        return []

    reports_table = _reports_qualified_table(mapping)
    tasks_key_col = mapping.get("reports_tasks_key", "tasks_key")
    geom_col = mapping.get("reports_geometry", "point")
    metric_srid = _metric_srid()

    query = f"""
        WITH order_poly AS (
            SELECT ST_GeomFromText(%s, {metric_srid}) AS geom
        )
        SELECT DISTINCT ON (r."{tasks_key_col}")
            r."{tasks_key_col}"::text AS task_key,
            r.id AS report_id,
            r.comment,
            r.created_at,
            r.username,
            ST_AsGeoJSON(ST_Transform(r."{geom_col}", 4326))::json AS geometry,
            to_jsonb(r) - '{geom_col}' AS row_json
        FROM {reports_table} r
        CROSS JOIN order_poly o
        WHERE r."{tasks_key_col}" IS NOT NULL
          AND r."{geom_col}" IS NOT NULL
          AND ST_Intersects(ST_Transform(r."{geom_col}", {metric_srid}), o.geom)
        ORDER BY r."{tasks_key_col}", r.id DESC
    """

    result: list[dict[str, Any]] = []
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (order_wkt,))
        rows = cur.fetchall()

    for row in rows:
        task_key = str(row["task_key"])
        geometry = row.get("geometry")
        if isinstance(geometry, str):
            geometry = json.loads(geometry)
        if not geometry:
            continue

        row_raw = row.get("row_json") or {}
        if isinstance(row_raw, str):
            row_raw = json.loads(row_raw)
        attrs = report_row_to_attributes(dict(row_raw))
        attrs["_task_key"] = task_key
        attrs["is_field_data"] = True

        comment = str(row.get("comment") or "").strip()
        label = comment or f"Отчёт #{row['report_id']}"
        created = _serialize_value(row.get("created_at"))

        result.append(
            {
                "task_key": task_key,
                "report_id": int(row["report_id"]),
                "source": "field_report",
                "group_name": "Разрытия",
                "subgroup_name": FIELD_DATA_SUBGROUP,
                "label": label,
                "attributes": attrs,
                "geometry": geometry,
                "sent_at": created,
            }
        )

    result.sort(key=lambda item: item.get("sent_at") or "", reverse=True)
    return result


def _track_task_key_expr(task_col: str) -> str:
    return f"""
        CASE
            WHEN position(':' IN NULLIF(TRIM(t."{task_col}"::text), '')) > 0
            THEN split_part(TRIM(t."{task_col}"::text), ':', 2)
            ELSE TRIM(t."{task_col}"::text)
        END
    """


def _fetch_order_tracks(
    conn: PgConnection,
    *,
    order_key: str,
    order_wkt: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    cfg = order_tracks_config()
    schema = cfg.get("schema", "mggt_field")
    table = cfg.get("table", "tracks")
    id_col = cfg.get("id_column", "id")
    geom_col = cfg.get("geometry_column", "geom")
    task_col = cfg.get("task_column", "task")
    metric_srid = _metric_srid()
    errors: list[str] = []

    track_geom = f'ST_Transform(t."{geom_col}", {metric_srid})'
    clipped_geom = f"""
        ST_LineMerge(
            ST_CollectionExtract(
                ST_Intersection({track_geom}, order_poly.geom),
                2
            )
        )
    """
    task_key_expr = _track_task_key_expr(task_col)

    query = f"""
        WITH order_poly AS (
            SELECT ST_GeomFromText(%s, {metric_srid}) AS geom
        )
        SELECT t."{id_col}"::text AS track_id,
               ST_AsGeoJSON(ST_Transform({clipped_geom}, 4326))::json AS geometry,
               ST_AsGeoJSON(
                   ST_Transform(
                       ST_Intersection(
                           ST_Buffer({track_geom}, {TRACK_BUFFER_METERS}),
                           order_poly.geom
                       ),
                       4326
                   )
               )::json AS buffer_geometry,
               row_to_json(t)::json AS row_json
        FROM "{schema}"."{table}" t
        CROSS JOIN order_poly
        WHERE t."{geom_col}" IS NOT NULL
          AND {task_key_expr} = %s
          AND ST_Intersects({track_geom}, order_poly.geom)
          AND NOT ST_IsEmpty({clipped_geom})
        ORDER BY t.created_at DESC NULLS LAST
        LIMIT 500
    """

    tracks: list[dict[str, Any]] = []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (order_wkt, order_key))
            for row in cur.fetchall():
                geometry = row.get("geometry")
                if isinstance(geometry, str):
                    geometry = json.loads(geometry)
                if not geometry:
                    continue
                buffer_geometry = row.get("buffer_geometry")
                if isinstance(buffer_geometry, str):
                    buffer_geometry = json.loads(buffer_geometry)
                row_raw = row.get("row_json") or {}
                if isinstance(row_raw, str):
                    row_raw = json.loads(row_raw)
                attrs = track_row_to_attributes(dict(row_raw), cfg)
                tracks.append(
                    {
                        "id": str(row["track_id"]),
                        "attributes": attrs,
                        "geometry": geometry,
                        "buffer_geometry": buffer_geometry,
                    }
                )
    except Exception as exc:
        errors.append(f"Треки заказа: {exc}")
        return [], errors

    return tracks, errors


def _compute_track_coverage_pct(
    conn: PgConnection,
    *,
    order_key: str,
    order_wkt: str,
    order_area_m2: float | None,
) -> float | None:
    if not order_area_m2 or order_area_m2 <= 0:
        return None

    cfg = order_tracks_config()
    schema = cfg.get("schema", "mggt_field")
    table = cfg.get("table", "tracks")
    geom_col = cfg.get("geometry_column", "geom")
    task_col = cfg.get("task_column", "task")
    metric_srid = _metric_srid()
    task_key_expr = _track_task_key_expr(task_col)
    track_geom = f'ST_Transform(t."{geom_col}", {metric_srid})'

    query = f"""
        WITH order_poly AS (
            SELECT ST_GeomFromText(%s, {metric_srid}) AS geom
        ),
        track_buf AS (
            SELECT ST_Union(ST_Buffer({track_geom}, {TRACK_BUFFER_METERS})) AS geom
            FROM "{schema}"."{table}" t
            CROSS JOIN order_poly
            WHERE t."{geom_col}" IS NOT NULL
              AND {task_key_expr} = %s
              AND ST_Intersects({track_geom}, order_poly.geom)
        )
        SELECT
            CASE
                WHEN tb.geom IS NULL OR ST_IsEmpty(tb.geom) THEN 0::float
                ELSE 100.0 * ST_Area(ST_Intersection(op.geom, tb.geom))
                     / NULLIF(ST_Area(op.geom), 0)
            END AS coverage_pct
        FROM order_poly op
        LEFT JOIN track_buf tb ON TRUE
    """
    try:
        with conn.cursor() as cur:
            cur.execute(query, (order_wkt, order_key))
            row = cur.fetchone()
        if not row or row[0] is None:
            return 0.0
        pct = float(row[0])
        return max(0.0, min(100.0, round(pct, 2)))
    except Exception:
        return None


def _fetch_saved_score(conn: PgConnection, order_key: str) -> dict[str, Any] | None:
    query = f"""
        SELECT
            order_key::text AS order_key,
            task_scores,
            track_coverage_pct,
            order_score,
            scored_by,
            scored_at,
            updated_at
        FROM "{FIELD_SCORE_SCHEMA}"."{FIELD_SCORE_TABLE}"
        WHERE order_key = %s::uuid
        LIMIT 1
    """
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (order_key,))
            row = cur.fetchone()
    except Exception:
        return None
    if not row:
        return None
    data = dict(row)
    scores = data.get("task_scores") or {}
    if isinstance(scores, str):
        scores = json.loads(scores)
    data["task_scores"] = {
        str(k): str(v)
        for k, v in dict(scores).items()
        if str(v) in SCORE_VALUES
    }
    if data.get("track_coverage_pct") is not None:
        data["track_coverage_pct"] = float(data["track_coverage_pct"])
    data["scored_at"] = _serialize_value(data.get("scored_at"))
    data["updated_at"] = _serialize_value(data.get("updated_at"))
    return data


def build_field_score_context(conn: PgConnection, order_key: str) -> dict[str, Any]:
    order = _fetch_order(conn, order_key)
    if order is None:
        raise FieldScoreError("Заказ не найден или без геометрии", status_code=404)

    order_wkt = order.pop("order_wkt")
    order_area_m2 = order.pop("order_area_m2", None)
    rayon = order.get("rayon")

    tasks = _fetch_closed_tasks(conn, order_wkt=order_wkt, rayon=rayon)
    tracks, track_errors = _fetch_order_tracks(
        conn, order_key=order_key, order_wkt=order_wkt
    )
    coverage_pct = _compute_track_coverage_pct(
        conn,
        order_key=order_key,
        order_wkt=order_wkt,
        order_area_m2=order_area_m2,
    )
    saved = _fetch_saved_score(conn, order_key)

    return {
        "order": {
            "order_key": order["order_key"],
            "task_number": order.get("task_number"),
            "rayon": order.get("rayon"),
            "area": order.get("area"),
            "status": order.get("status"),
            "date_survey": order.get("date_survey"),
            "geometry": order.get("geometry"),
        },
        "tasks": tasks,
        "tracks": tracks,
        "track_coverage_pct": coverage_pct,
        "coverage_hint": coverage_hint_from_pct(coverage_pct),
        "buffer_meters": TRACK_BUFFER_METERS,
        "saved": saved,
        "errors": track_errors,
    }


def _normalize_task_scores(raw: dict[str, Any] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in dict(raw or {}).items():
        score = str(value).strip()
        if score not in SCORE_VALUES:
            raise FieldScoreError(
                f"Недопустимая оценка задачи {key}: {value}",
                status_code=400,
            )
        result[str(key)] = score
    return result


def upsert_field_score(
    conn: PgConnection,
    *,
    order_key: str,
    scored_by: str,
    task_scores: dict[str, Any] | None,
    order_score: str | None,
) -> dict[str, Any]:
    login = (scored_by or "").strip()
    if not login:
        raise FieldScoreError("Не указан пользователь", status_code=400)

    context = build_field_score_context(conn, order_key)
    task_keys = {t["task_key"] for t in context["tasks"]}
    normalized_scores = _normalize_task_scores(task_scores)

    unknown = set(normalized_scores) - task_keys
    if unknown:
        raise FieldScoreError(
            f"Оценки для задач вне заказа: {', '.join(sorted(unknown)[:5])}",
            status_code=400,
        )

    score_value = (order_score or "").strip() or None
    if score_value is not None and score_value not in SCORE_VALUES:
        raise FieldScoreError(f"Недопустимая оценка заказа: {order_score}", status_code=400)

    if score_value is not None:
        missing = sorted(task_keys - set(normalized_scores))
        if missing:
            raise FieldScoreError(
                "Сначала оцените все задачи, затем оценку заказа",
                status_code=400,
            )

    coverage_pct = context.get("track_coverage_pct")
    now = datetime.now(timezone.utc)

    query = f"""
        INSERT INTO "{FIELD_SCORE_SCHEMA}"."{FIELD_SCORE_TABLE}" (
            order_key, task_scores, track_coverage_pct, order_score,
            scored_by, scored_at, updated_at
        )
        VALUES (
            %s::uuid, %s::jsonb, %s, %s, %s, %s, %s
        )
        ON CONFLICT (order_key) DO UPDATE SET
            task_scores = EXCLUDED.task_scores,
            track_coverage_pct = EXCLUDED.track_coverage_pct,
            order_score = EXCLUDED.order_score,
            scored_by = EXCLUDED.scored_by,
            updated_at = EXCLUDED.updated_at
        RETURNING
            order_key::text AS order_key,
            task_scores,
            track_coverage_pct,
            order_score,
            scored_by,
            scored_at,
            updated_at
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            query,
            (
                order_key,
                Json(normalized_scores),
                coverage_pct,
                score_value,
                login,
                now,
                now,
            ),
        )
        row = cur.fetchone()
    conn.commit()

    data = dict(row)
    scores = data.get("task_scores") or {}
    if isinstance(scores, str):
        scores = json.loads(scores)
    data["task_scores"] = dict(scores)
    if data.get("track_coverage_pct") is not None:
        data["track_coverage_pct"] = float(data["track_coverage_pct"])
    data["scored_at"] = _serialize_value(data.get("scored_at"))
    data["updated_at"] = _serialize_value(data.get("updated_at"))
    data["coverage_hint"] = coverage_hint_from_pct(
        float(data["track_coverage_pct"]) if data.get("track_coverage_pct") is not None else None
    )
    return data
